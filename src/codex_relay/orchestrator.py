from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from .commanding import CommandKind, ParsedCommand, parse_command
from .models import InboundMessage, RunState
from .protocols import ConnectorProtocol, EgressProtocol, StoreProtocol
from .voice_memo import cleanup_voice_memo, generate_voice_memo


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
        workspace_aliases: dict[str, str] | None = None,
        auto_context_messages: int = 0,
        enable_progress_streaming: bool = False,
        progress_update_interval_seconds: float = 30.0,
        enable_attachments: bool = False,
        enable_voice_memos: bool = False,
        voice_memo_voice: str = "Samantha",
        voice_memo_max_chars: int = 2000,
        voice_memo_send_text_too: bool = True,
        voice_memo_output_dir: str = "/tmp/codex_relay_attachments",
    ):
        self.connector = connector
        self.egress = egress
        self.store = store
        self.allowed_workspaces = [str(Path(p).resolve()) for p in allowed_workspaces]
        self.default_workspace = str(Path(default_workspace).resolve())
        self.approval_ttl_minutes = approval_ttl_minutes
        self.require_chat_prefix = require_chat_prefix
        self.chat_prefix = (chat_prefix or "relay:").strip()
        self.workspace_aliases = workspace_aliases or {}
        self.auto_context_messages = auto_context_messages
        self.enable_progress_streaming = enable_progress_streaming
        self.progress_update_interval_seconds = progress_update_interval_seconds
        self.enable_attachments = enable_attachments
        self.enable_voice_memos = enable_voice_memos
        self.voice_memo_voice = voice_memo_voice
        self.voice_memo_max_chars = voice_memo_max_chars
        self.voice_memo_send_text_too = voice_memo_send_text_too
        self.voice_memo_output_dir = voice_memo_output_dir

    # --- Workspace Resolution (Feature 1) ---

    def _resolve_workspace(self, alias: str) -> str:
        """Resolve a workspace alias to an absolute path."""
        if not alias:
            return self.default_workspace
        resolved = self.workspace_aliases.get(alias)
        if resolved and self._is_workspace_allowed(resolved):
            return resolved
        return self.default_workspace

    # --- Main Handler ---

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
                    "Or use `idea:`, `plan:`, `task:`, `project:`, `health`, or `history:`."
                )
                self.egress.send(message.sender, hint)
                return OrchestrationResult(kind=CommandKind.CHAT, response=hint)

        if command.kind is CommandKind.HEALTH:
            return self._handle_health(message.sender)

        if command.kind is CommandKind.HISTORY:
            return self._handle_history(message.sender, command.payload)

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

        workspace = self._resolve_workspace(command.workspace)

        thread_id = self.connector.get_or_create_thread(message.sender)
        self.store.upsert_session(message.sender, thread_id, command.kind.value)

        if command.kind in {CommandKind.TASK, CommandKind.PROJECT}:
            return self._handle_approval_required_command(message, command.kind, thread_id, command.payload, workspace)

        prompt = self._build_non_mutating_prompt(command.kind, command.payload, workspace)
        prompt = self._inject_auto_context(message.sender, prompt)
        prompt = self._inject_attachment_context(message, prompt)

        response = self.connector.run_turn(thread_id, prompt)
        if self.enable_voice_memos and not self.voice_memo_send_text_too:
            self._send_voice_memo(message.sender, response)
        else:
            self.egress.send(message.sender, response)
            self._send_voice_memo(message.sender, response)
        return OrchestrationResult(kind=command.kind, response=response)

    # --- Feature 2: Health Dashboard ---

    def _handle_health(self, sender: str) -> OrchestrationResult:
        parts = ["Codex Relay Health"]

        if hasattr(self.store, "get_stats"):
            stats = self.store.get_stats()
            parts.append(f"Sessions: {stats.get('active_sessions', '?')}")
            parts.append(f"Messages processed: {stats.get('total_messages', '?')}")
            parts.append(f"Pending approvals: {stats.get('pending_approvals', '?')}")
            runs = stats.get("runs_by_state", {})
            if runs:
                runs_str = ", ".join(f"{state}: {count}" for state, count in sorted(runs.items()))
                parts.append(f"Runs: {runs_str}")
        else:
            pending = self.store.list_pending_approvals()
            parts.append(f"Pending approvals: {len(pending)}")

        started_at = self.store.get_state("daemon_started_at")
        if started_at:
            try:
                start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=UTC)
                uptime = datetime.now(UTC) - start_dt
                hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                minutes = remainder // 60
                parts.append(f"Uptime: {hours}h {minutes}m")
            except (ValueError, TypeError):
                pass

        response = "\n".join(parts)
        self.egress.send(sender, response)
        return OrchestrationResult(kind=CommandKind.HEALTH, response=response)

    # --- Feature 3: Conversation Memory ---

    def _handle_history(self, sender: str, query: str) -> OrchestrationResult:
        if query and hasattr(self.store, "search_messages"):
            results = self.store.search_messages(sender, query, limit=10)
            if not results:
                response = f"No messages found matching '{query}'."
            else:
                lines = [f"Messages matching '{query}' ({len(results)} found):"]
                for msg in results:
                    text_preview = (msg.get("text", ""))[:80]
                    received = msg.get("received_at", "?")
                    lines.append(f"  [{received}] {text_preview}")
                response = "\n".join(lines)
        elif hasattr(self.store, "recent_messages"):
            results = self.store.recent_messages(sender, limit=10)
            if not results:
                response = "No message history found."
            else:
                lines = [f"Recent messages ({len(results)}):"]
                for msg in results:
                    text_preview = (msg.get("text", ""))[:80]
                    received = msg.get("received_at", "?")
                    lines.append(f"  [{received}] {text_preview}")
                response = "\n".join(lines)
        else:
            response = "History not available (store does not support message queries)."

        self.egress.send(sender, response)
        return OrchestrationResult(kind=CommandKind.HISTORY, response=response)

    def _inject_auto_context(self, sender: str, prompt: str) -> str:
        if self.auto_context_messages <= 0:
            return prompt
        if not hasattr(self.store, "recent_messages"):
            return prompt
        recent = self.store.recent_messages(sender, limit=self.auto_context_messages)
        if not recent:
            return prompt
        context_lines = []
        for msg in reversed(recent):
            context_lines.append(f"[{msg.get('received_at', '?')}] {msg.get('text', '')[:200]}")
        context_block = "\n".join(context_lines)
        return f"Recent conversation history:\n{context_block}\n\n{prompt}"

    # --- Feature 8: Attachment Context ---

    def _inject_attachment_context(self, message: InboundMessage, prompt: str) -> str:
        if not self.enable_attachments:
            return prompt
        attachments = message.context.get("attachments", [])
        if not attachments:
            return prompt
        attachment_lines = []
        for att in attachments:
            filename = att.get("filename", "unknown")
            mime = att.get("mime_type", "unknown")
            path = att.get("path", "")
            attachment_lines.append(f"  - {filename} ({mime}) at {path}")
        attachment_block = "\n".join(attachment_lines)
        return f"{prompt}\n\nAttached files:\n{attachment_block}"

    # --- Approval Workflow ---

    def _resolve_approval(self, sender: str, kind: CommandKind, request_id: str) -> OrchestrationResult:
        approval = self.store.get_approval(request_id)
        if not approval:
            response = f"Unknown request id: {request_id}"
            self.egress.send(sender, response)
            return OrchestrationResult(kind=kind, response=response)

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

        if self.enable_progress_streaming and hasattr(self.connector, "run_turn_streaming"):
            execution_output = self._run_with_progress(sender, thread_id, exec_prompt)
        else:
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
        self._send_voice_memo(sender, verification_output)
        return OrchestrationResult(kind=kind, run_id=approval["run_id"], response=final)

    def _handle_approval_required_command(
        self,
        message: InboundMessage,
        kind: CommandKind,
        thread_id: str,
        payload: str,
        workspace: str | None = None,
    ) -> OrchestrationResult:
        ws = workspace or self.default_workspace
        if not self._is_workspace_allowed(ws):
            response = (
                f"Workspace blocked by policy: {ws}. "
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
            cwd=ws,
            risk_level="execute",
        )

        planner_prompt = (
            "planner mode: produce an objective, steps, risks, and done criteria. "
            f"intent={kind.value}; request={payload}; workspace={ws}"
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

    # --- Feature 7: Progress Streaming ---

    def _run_with_progress(self, sender: str, thread_id: str, prompt: str) -> str:
        last_update = time.monotonic()

        def on_progress(line: str) -> None:
            nonlocal last_update
            now = time.monotonic()
            if (now - last_update) >= self.progress_update_interval_seconds:
                preview = line.strip()[:200]
                if preview:
                    self.egress.send(sender, f"[Progress] {preview}")
                last_update = now

        return self.connector.run_turn_streaming(thread_id, prompt, on_progress)

    # --- Voice Memo ---

    def _send_voice_memo(self, sender: str, text: str) -> None:
        """Generate and send a voice memo for the given text."""
        if not self.enable_voice_memos:
            return
        if not hasattr(self.egress, "send_attachment"):
            return
        memo_path = generate_voice_memo(
            text=text,
            output_dir=self.voice_memo_output_dir,
            voice=self.voice_memo_voice,
            max_chars=self.voice_memo_max_chars,
        )
        if memo_path:
            try:
                self.egress.send_attachment(sender, memo_path)
            finally:
                cleanup_voice_memo(memo_path)

    # --- Prompt Building ---

    def _build_non_mutating_prompt(self, kind: CommandKind, payload: str, workspace: str | None = None) -> str:
        ws = workspace or self.default_workspace
        if kind is CommandKind.CHAT:
            return (
                "You are Codex Relay over iMessage for a coding workspace. "
                f"Workspace path: {ws}. "
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
