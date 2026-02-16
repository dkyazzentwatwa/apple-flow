from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from .commanding import CommandKind, ParsedCommand, parse_command
from .models import InboundMessage, RunState
from .protocols import ConnectorProtocol, EgressProtocol, StoreProtocol


@dataclass(slots=True)
class OrchestrationResult:
    kind: CommandKind
    run_id: str | None = None
    approval_request_id: str | None = None
    response: str | None = None


class RelayOrchestrator:
    def __init__(
        self,
        connector: ConnectorProtocol,
        egress: EgressProtocol,
        store: StoreProtocol,
        allowed_workspaces: list[str],
        default_workspace: str,
        approval_ttl_minutes: int = 20,
        require_chat_prefix: bool = True,
        chat_prefix: str = "relay:",
    ):
        self.connector = connector
        self.egress = egress
        self.store = store
        self.allowed_workspaces = [str(Path(p).resolve()) for p in allowed_workspaces]
        self.default_workspace = str(Path(default_workspace).resolve())
        self.approval_ttl_minutes = approval_ttl_minutes
        self.require_chat_prefix = require_chat_prefix
        self.chat_prefix = (chat_prefix or "relay:").strip()

    def handle_message(self, message: InboundMessage) -> OrchestrationResult:
        dedupe_hash = sha256(f"{message.sender}:{message.id}:{message.text}".encode()).hexdigest()
        inserted = True
        if hasattr(self.store, "record_message"):
            inserted = self.store.record_message(
                message_id=message.id,
                sender=message.sender,
                text=message.text,
                received_at=message.received_at,
                dedupe_hash=dedupe_hash,
            )
        if not inserted:
            return OrchestrationResult(kind=CommandKind.STATUS, response="duplicate")

        raw_text = message.text.strip()
        if not raw_text:
            return OrchestrationResult(kind=CommandKind.CHAT, response="ignored_empty")

        command = parse_command(raw_text)
        if command.kind is CommandKind.CHAT and self.require_chat_prefix:
            if not raw_text.lower().startswith(self.chat_prefix.lower()):
                return OrchestrationResult(kind=CommandKind.CHAT, response="ignored_missing_chat_prefix")
            command = ParsedCommand(
                kind=CommandKind.CHAT,
                payload=raw_text[len(self.chat_prefix) :].strip(),
            )
            if not command.payload:
                hint = (
                    f"Use `{self.chat_prefix} <message>` for general chat.\n"
                    "Or use `idea:`, `plan:`, `task:`, or `project:`."
                )
                self.egress.send(message.sender, hint)
                return OrchestrationResult(kind=CommandKind.CHAT, response=hint)

        if command.kind is CommandKind.STATUS:
            pending = self.store.list_pending_approvals()
            response = f"Pending approvals: {len(pending)}"
            self.egress.send(message.sender, response)
            return OrchestrationResult(kind=command.kind, response=response)

        if command.kind is CommandKind.CLEAR_CONTEXT:
            if hasattr(self.connector, "reset_thread"):
                thread_id = self.connector.reset_thread(message.sender)
            else:
                thread_id = self.connector.get_or_create_thread(message.sender)
            self.store.upsert_session(message.sender, thread_id, CommandKind.CHAT.value)
            response = "Started a fresh chat context for this sender."
            self.egress.send(message.sender, response)
            return OrchestrationResult(kind=command.kind, response=response)

        if command.kind in {CommandKind.APPROVE, CommandKind.DENY}:
            return self._resolve_approval(message.sender, command.kind, command.payload)

        thread_id = self.connector.get_or_create_thread(message.sender)
        self.store.upsert_session(message.sender, thread_id, command.kind.value)

        if command.kind in {CommandKind.TASK, CommandKind.PROJECT}:
            return self._handle_approval_required_command(message, command.kind, thread_id, command.payload)

        prompt = self._build_non_mutating_prompt(command.kind, command.payload)
        response = self.connector.run_turn(thread_id, prompt)
        self.egress.send(message.sender, response)
        return OrchestrationResult(kind=command.kind, response=response)

    def _resolve_approval(self, sender: str, kind: CommandKind, request_id: str) -> OrchestrationResult:
        approval = self.store.get_approval(request_id)
        if not approval:
            response = f"Unknown request id: {request_id}"
            self.egress.send(sender, response)
            return OrchestrationResult(kind=kind, response=response)

        # Security: verify the sender matches the original requester
        approval_sender = approval.get("sender")
        if approval_sender and approval_sender != sender:
            response = f"Only the original requester can {kind.value} request {request_id}."
            self.egress.send(sender, response)
            return OrchestrationResult(kind=kind, response=response)

        if kind is CommandKind.DENY:
            self.store.resolve_approval(request_id, "denied")
            self.store.update_run_state(approval["run_id"], RunState.DENIED.value)
            self._create_event(
                run_id=approval["run_id"],
                step="approval",
                event_type="denied",
                payload={"request_id": request_id},
            )
            response = f"Denied request {request_id}."
            self.egress.send(sender, response)
            return OrchestrationResult(kind=kind, run_id=approval["run_id"], response=response)

        expires_at = self._parse_dt(approval.get("expires_at"))
        if expires_at is not None and datetime.now(UTC) > expires_at:
            self.store.resolve_approval(request_id, "expired")
            self.store.update_run_state(approval["run_id"], RunState.FAILED.value)
            response = f"Approval request {request_id} expired. Send a new task/project request."
            self.egress.send(sender, response)
            return OrchestrationResult(kind=kind, run_id=approval["run_id"], response=response)

        self.store.resolve_approval(request_id, "approved")
        self.store.update_run_state(approval["run_id"], RunState.EXECUTING.value)
        self._create_event(
            run_id=approval["run_id"],
            step="approval",
            event_type="approved",
            payload={"request_id": request_id},
        )
        run = self.store.get_run(approval["run_id"])
        if run is None:
            response = f"Request {request_id} approved, but run was not found."
            self.egress.send(sender, response)
            return OrchestrationResult(kind=kind, response=response)

        thread_id = self.connector.get_or_create_thread(sender)
        exec_prompt = (
            "executor mode: perform the approved plan carefully and provide concise progress + final output. "
            f"workspace={run['cwd']}"
        )
        execution_output = self.connector.run_turn(thread_id, exec_prompt)
        self.store.update_run_state(approval["run_id"], RunState.VERIFYING.value)
        self._create_event(
            run_id=approval["run_id"],
            step="executor",
            event_type="completed",
            payload={"snippet": execution_output[:200]},
        )

        verify_prompt = "verifier mode: validate completion evidence and summarize pass/fail with key checks."
        verification_output = self.connector.run_turn(thread_id, verify_prompt)

        self.store.update_run_state(approval["run_id"], RunState.COMPLETED.value)
        self._create_event(
            run_id=approval["run_id"],
            step="verifier",
            event_type="completed",
            payload={"snippet": verification_output[:200]},
        )
        final = f"Execution:\n{execution_output}\n\nVerification:\n{verification_output}"
        self.egress.send(sender, final)
        return OrchestrationResult(kind=kind, run_id=approval["run_id"], response=final)

    def _handle_approval_required_command(
        self,
        message: InboundMessage,
        kind: CommandKind,
        thread_id: str,
        payload: str,
    ) -> OrchestrationResult:
        if not self._is_workspace_allowed(self.default_workspace):
            response = (
                f"Workspace blocked by policy: {self.default_workspace}. "
                "Ask the admin to add it to allowed_workspaces."
            )
            self.egress.send(message.sender, response)
            return OrchestrationResult(kind=kind, response=response)

        run_id = f"run_{uuid4().hex[:12]}"
        self.store.create_run(
            run_id=run_id,
            sender=message.sender,
            intent=kind.value,
            state=RunState.PLANNING.value,
            cwd=self.default_workspace,
            risk_level="execute",
        )

        planner_prompt = (
            "planner mode: produce an objective, steps, risks, and done criteria. "
            f"intent={kind.value}; request={payload}; workspace={self.default_workspace}"
        )
        plan_output = self.connector.run_turn(thread_id, planner_prompt)

        self.store.update_run_state(run_id, RunState.AWAITING_APPROVAL.value)
        request_id = f"req_{uuid4().hex[:8]}"
        expires_at = (datetime.now(UTC) + timedelta(minutes=self.approval_ttl_minutes)).isoformat()
        self.store.create_approval(
            request_id=request_id,
            run_id=run_id,
            summary=f"{kind.value} execution requires approval",
            command_preview=plan_output[:800],
            expires_at=expires_at,
            sender=message.sender,
        )
        self._create_event(
            run_id=run_id,
            step="planner",
            event_type="awaiting_approval",
            payload={"request_id": request_id, "plan_snippet": plan_output[:200]},
        )

        outbound = (
            f"Plan for {kind.value}:\n{plan_output}\n\n"
            f"Approve with: approve {request_id}\n"
            f"Deny with: deny {request_id}"
        )
        self.egress.send(message.sender, outbound)
        return OrchestrationResult(kind=kind, run_id=run_id, approval_request_id=request_id, response=outbound)

    def _build_non_mutating_prompt(self, kind: CommandKind, payload: str) -> str:
        if kind is CommandKind.CHAT:
            return (
                "You are Codex Relay over iMessage for a coding workspace. "
                f"Workspace path: {self.default_workspace}. "
                "Answer the user's exact request directly. "
                "If they ask about files/directories, inspect the workspace and return concrete results. "
                "Do not send generic readiness lines like 'I'm here and ready'. "
                "Do not mention internal policies, skills, hidden instructions, or bootstrap steps unless asked.\n\n"
                f"User message: {payload}"
            )
        if kind is CommandKind.IDEA:
            return f"brainstorm mode: generate options, trade-offs, and recommendation. request={payload}"
        if kind is CommandKind.PLAN:
            return f"planning mode: create a stepwise implementation plan with acceptance criteria. goal={payload}"
        return payload

    def _is_workspace_allowed(self, candidate: str) -> bool:
        target = str(Path(candidate).resolve())
        for allowed in self.allowed_workspaces:
            allowed_path = Path(allowed)
            if str(allowed_path) == target or allowed_path in Path(target).parents:
                return True
        return False

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            return None

    def _create_event(self, run_id: str, step: str, event_type: str, payload: dict[str, Any]) -> None:
        if hasattr(self.store, "create_event"):
            self.store.create_event(
                event_id=f"evt_{uuid4().hex[:12]}",
                run_id=run_id,
                step=step,
                event_type=event_type,
                payload=payload,
            )
