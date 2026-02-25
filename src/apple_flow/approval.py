"""Approval workflow handler — extracted from orchestrator.py."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .commanding import CommandKind
from .models import InboundMessage, RunState
from .notes_logging import log_to_notes
from .protocols import ConnectorProtocol, EgressProtocol, StoreProtocol
from .utils import normalize_sender

if TYPE_CHECKING:
    from .scheduler import FollowUpScheduler

logger = logging.getLogger("apple_flow.approval")


@dataclass(slots=True)
class OrchestrationResult:
    kind: CommandKind
    run_id: str | None = None
    approval_request_id: str | None = None
    response: str | None = None


class ApprovalHandler:
    """Encapsulates the approve/deny workflow and post-execution cleanup."""

    def __init__(
        self,
        connector: ConnectorProtocol,
        egress: EgressProtocol,
        store: StoreProtocol,
        approval_ttl_minutes: int,
        enable_progress_streaming: bool,
        progress_update_interval_seconds: float,
        execution_heartbeat_seconds: float,
        checkpoint_on_timeout: bool,
        max_resume_attempts: int,
        enable_verifier: bool,
        reminders_egress: Any,
        reminders_archive_list_name: str,
        notes_egress: Any,
        notes_archive_folder_name: str,
        calendar_egress: Any,
        scheduler: FollowUpScheduler | None,
        log_notes_egress: Any,
        notes_log_folder_name: str,
        approval_sender_override: str = "",
    ) -> None:
        self.connector = connector
        self.egress = egress
        self.store = store
        self.approval_ttl_minutes = approval_ttl_minutes
        self.enable_progress_streaming = enable_progress_streaming
        self.progress_update_interval_seconds = progress_update_interval_seconds
        self.execution_heartbeat_seconds = max(5.0, execution_heartbeat_seconds)
        self.checkpoint_on_timeout = checkpoint_on_timeout
        self.max_resume_attempts = max(1, max_resume_attempts)
        self.enable_verifier = enable_verifier
        self.reminders_egress = reminders_egress
        self.reminders_archive_list_name = reminders_archive_list_name
        self.notes_egress = notes_egress
        self.notes_archive_folder_name = notes_archive_folder_name
        self.calendar_egress = calendar_egress
        self.scheduler = scheduler
        self.log_notes_egress = log_notes_egress
        self.notes_log_folder_name = notes_log_folder_name
        self.approval_sender_override = approval_sender_override

    # --- Public API ---

    def resolve(self, sender: str, kind: CommandKind, payload: str) -> OrchestrationResult:
        """Handle an approve or deny command."""
        parts = payload.split(None, 1)
        if not parts:
            response = f"Usage: `{kind.value} <request_id>`"
            self._safe_send(sender, response)
            return OrchestrationResult(kind=kind, response=response)

        request_id = parts[0]
        extra_instructions = parts[1].strip() if len(parts) > 1 else ""
        approval = self.store.get_approval(request_id)
        if not approval:
            response = f"Unknown request id: {request_id}"
            self._safe_send(sender, response)
            return OrchestrationResult(kind=kind, response=response)

        run_id = approval.get("run_id")

        try:
            return self._resolve_inner(
                sender=sender,
                kind=kind,
                request_id=request_id,
                extra_instructions=extra_instructions,
                approval=approval,
            )
        except Exception as exc:
            logger.exception(
                "Unhandled approval flow error request_id=%s run_id=%s: %s",
                request_id,
                run_id,
                exc,
            )
            if run_id:
                self.store.update_run_state(run_id, RunState.FAILED.value)
                self._create_event(
                    run_id=run_id,
                    step="executor",
                    event_type="execution_failed",
                    payload={"request_id": request_id, "reason": f"{type(exc).__name__}: {exc}"},
                )
            response = (
                "⚠️ I hit an internal error while processing that approval. "
                "The run was marked failed. Send `status` for details and retry with a new task if needed."
            )
            self._safe_send(sender, response)
            return OrchestrationResult(kind=kind, run_id=run_id, response=response)

    def _resolve_inner(
        self,
        sender: str,
        kind: CommandKind,
        request_id: str,
        extra_instructions: str,
        approval: dict[str, Any],
    ) -> OrchestrationResult:
        approval_sender = approval.get("sender")
        if approval_sender and normalize_sender(approval_sender) != normalize_sender(sender):
            logger.debug(
                "Approval sender mismatch: approval_sender=%r (normalized=%r), "
                "request_sender=%r (normalized=%r)",
                approval_sender, normalize_sender(approval_sender),
                sender, normalize_sender(sender),
            )
            response = f"Only the original requester can {kind.value} request {request_id}."
            self._safe_send(sender, response)
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
            self._safe_send(sender, response)
            return OrchestrationResult(kind=kind, run_id=approval["run_id"], response=response)

        expires_at = self._parse_dt(approval.get("expires_at"))
        if expires_at is not None and datetime.now(UTC) > expires_at:
            self.store.resolve_approval(request_id, "expired")
            self.store.update_run_state(approval["run_id"], RunState.FAILED.value)
            response = f"Approval request {request_id} expired. Send a new task/project request."
            self._safe_send(sender, response)
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
            self._safe_send(sender, response)
            return OrchestrationResult(kind=kind, response=response)

        attempt = self._next_attempt(approval["run_id"])
        self._create_event(
            run_id=approval["run_id"],
            step="executor",
            event_type="execution_started",
            payload={"request_id": request_id, "attempt": attempt},
        )
        self._safe_send(
            sender,
            (
                f"✅ Approved {request_id}. Starting execution "
                f"(attempt {attempt}/{self.max_resume_attempts})."
            ),
        )

        thread_id = self.connector.get_or_create_thread(sender)

        plan_summary = approval.get("command_preview", "")
        exec_prompt_parts = [
            "executor mode: perform the approved plan carefully and provide concise progress + final output.",
            "If blocked on input/credentials/decision, prefix your response with `BLOCKER:` and ask one clear question.",
            f"workspace={run['cwd']}",
        ]
        if plan_summary:
            exec_prompt_parts.append(f"approved plan:\n{plan_summary}")
        if extra_instructions:
            exec_prompt_parts.append(f"additional instructions from user: {extra_instructions}")
        exec_prompt = "\n".join(exec_prompt_parts)

        execution_output = self._run_execution(
            sender=sender,
            thread_id=thread_id,
            prompt=exec_prompt,
            run_id=approval["run_id"],
            step="executor",
            phase=f"execution attempt {attempt}",
        )

        outcome, reason = self._classify_execution_outcome(execution_output)
        should_checkpoint = self._should_checkpoint(outcome=outcome, attempt=attempt)
        if should_checkpoint:
            checkpoint_message, checkpoint_request_id = self._checkpoint_run(
                sender=sender,
                run_id=approval["run_id"],
                attempt=attempt,
                reason=reason,
                output=execution_output,
                approval_sender=approval.get("sender", sender),
                previous_request_id=request_id,
            )
            self._log(kind.value, sender, run.get("intent", ""), checkpoint_message)
            return OrchestrationResult(
                kind=kind,
                run_id=approval["run_id"],
                approval_request_id=checkpoint_request_id,
                response=checkpoint_message,
            )

        self._create_event(
            run_id=approval["run_id"],
            step="executor",
            event_type="completed" if outcome == "success" else "execution_failed",
            payload={"reason": reason, "snippet": execution_output[:200]},
        )

        if outcome != "success":
            self.store.update_run_state(approval["run_id"], RunState.FAILED.value)
            final = f"❌ Execution failed ({reason}).\n\n{execution_output}"
            self._safe_send(sender, final)
            self._log(kind.value, sender, run.get("intent", ""), final)
            return OrchestrationResult(kind=kind, run_id=approval["run_id"], response=final)

        if self.enable_verifier:
            self.store.update_run_state(approval["run_id"], RunState.VERIFYING.value)
            verify_prompt = "verifier mode: validate completion evidence and summarize pass/fail with key checks."
            verification_output = self._run_execution(
                sender=sender,
                thread_id=thread_id,
                prompt=verify_prompt,
                run_id=approval["run_id"],
                step="verifier",
                phase=f"verification attempt {attempt}",
            )
            verifier_outcome, verifier_reason = self._classify_execution_outcome(verification_output)
            self._create_event(
                run_id=approval["run_id"],
                step="verifier",
                event_type="completed" if verifier_outcome == "success" else "execution_failed",
                payload={"reason": verifier_reason, "snippet": verification_output[:200]},
            )
            if verifier_outcome != "success":
                self.store.update_run_state(approval["run_id"], RunState.FAILED.value)
                final = (
                    f"❌ Verification failed ({verifier_reason}).\n\n"
                    f"Execution:\n{execution_output}\n\nVerification:\n{verification_output}"
                )
                self._safe_send(sender, final)
                self._log(kind.value, sender, run.get("intent", ""), final)
                return OrchestrationResult(kind=kind, run_id=approval["run_id"], response=final)
            final = f"Execution:\n{execution_output}\n\nVerification:\n{verification_output}"
        else:
            final = execution_output

        self.store.update_run_state(approval["run_id"], RunState.COMPLETED.value)
        self._safe_send(sender, final)
        self._log(kind.value, sender, run.get("intent", ""), final)

        source_context = self.store.get_run_source_context(approval["run_id"])
        if source_context:
            self._handle_post_execution_cleanup(source_context, final)

        if self.scheduler:
            try:
                self.scheduler.schedule(
                    run_id=approval["run_id"],
                    sender=sender,
                    action_type="follow_up",
                    payload={"summary": f"Follow up on approved task {request_id}"},
                )
            except Exception as exc:
                logger.debug("Failed to schedule follow-up: %s", exc)

        return OrchestrationResult(kind=kind, run_id=approval["run_id"], response=final)

    def handle_approval_required(
        self,
        message: InboundMessage,
        kind: CommandKind,
        thread_id: str,
        payload: str,
        workspace: str,
        default_workspace: str,
        is_workspace_allowed: Any,
    ) -> OrchestrationResult:
        """Plan a mutating command and create an approval request."""
        ws = workspace or default_workspace
        if not is_workspace_allowed(ws):
            response = (
                f"Workspace blocked by policy: {ws}. "
                "Ask the admin to add it to allowed_workspaces."
            )
            self._safe_send(message.sender, response)
            return OrchestrationResult(kind=kind, response=response)

        run_id = f"run_{uuid4().hex[:12]}"

        source_context = None
        if message.context:
            channel = message.context.get("channel")
            if channel == "reminders":
                source_context = {
                    "channel": "reminders",
                    "reminder_id": message.context.get("reminder_id"),
                    "reminder_name": message.context.get("reminder_name"),
                    "list_name": message.context.get("list_name"),
                }
            elif channel == "notes":
                source_context = {
                    "channel": "notes",
                    "note_id": message.context.get("note_id"),
                    "note_name": message.context.get("note_title"),
                    "folder_name": message.context.get("folder_name"),
                }
            elif channel == "calendar":
                source_context = {
                    "channel": "calendar",
                    "event_id": message.context.get("event_id"),
                    "event_name": message.context.get("event_summary"),
                    "calendar_name": message.context.get("calendar_name"),
                }

        self.store.create_run(
            run_id=run_id,
            sender=message.sender,
            intent=kind.value,
            state=RunState.PLANNING.value,
            cwd=ws,
            risk_level="execute",
            source_context=source_context,
        )

        planner_prompt = (
            "planner mode: produce an objective, steps, risks, and done criteria. "
            f"intent={kind.value}; request={payload}; workspace={ws}"
        )
        plan_output = self.connector.run_turn(thread_id, planner_prompt)

        self.store.update_run_state(run_id, RunState.AWAITING_APPROVAL.value)
        request_id = f"req_{uuid4().hex[:8]}"
        expires_at = (datetime.now(UTC) + timedelta(minutes=self.approval_ttl_minutes)).isoformat()
        approval_sender = self.approval_sender_override or message.sender
        self.store.create_approval(
            request_id=request_id,
            run_id=run_id,
            summary=f"{kind.value} execution requires approval",
            command_preview=plan_output[:800],
            expires_at=expires_at,
            sender=approval_sender,
        )
        self._create_event(
            run_id=run_id,
            step="planner",
            event_type="awaiting_approval",
            payload={"request_id": request_id, "plan_snippet": plan_output[:200]},
        )

        outbound = (
            f"Here's my plan:\n{plan_output}\n\n"
            f"Reply `approve {request_id}` to proceed, or `deny {request_id}` to cancel."
        )
        self._safe_send(message.sender, outbound)
        self._log(kind.value, message.sender, payload, outbound)
        return OrchestrationResult(kind=kind, run_id=run_id, approval_request_id=request_id, response=outbound)

    # --- Internal helpers ---

    def _run_execution(
        self,
        sender: str,
        thread_id: str,
        prompt: str,
        run_id: str,
        step: str,
        phase: str,
    ) -> str:
        if self.enable_progress_streaming and hasattr(self.connector, "run_turn_streaming"):
            return self._run_with_progress(sender, thread_id, prompt, run_id=run_id, step=step, phase=phase)
        return self._run_with_heartbeat(
            sender=sender,
            runner=lambda: self.connector.run_turn(thread_id, prompt),
            run_id=run_id,
            step=step,
            phase=phase,
        )

    def _run_with_progress(
        self,
        sender: str,
        thread_id: str,
        prompt: str,
        run_id: str,
        step: str,
        phase: str,
    ) -> str:
        last_update = 0.0

        def on_progress(line: str) -> None:
            nonlocal last_update
            now = time.monotonic()
            if (now - last_update) >= self.progress_update_interval_seconds:
                preview = line.strip()[:200]
                if preview:
                    self._safe_send(sender, f"[Progress] {preview}")
                    self._create_event(
                        run_id=run_id,
                        step=step,
                        event_type="progress",
                        payload={"phase": phase, "snippet": preview},
                    )
                last_update = now

        return self._run_with_heartbeat(
            sender=sender,
            runner=lambda: self.connector.run_turn_streaming(thread_id, prompt, on_progress),
            run_id=run_id,
            step=step,
            phase=phase,
        )

    def _run_with_heartbeat(
        self,
        sender: str,
        runner: Any,
        run_id: str,
        step: str,
        phase: str,
    ) -> str:
        done = threading.Event()
        result: dict[str, str] = {}
        error: dict[str, Exception] = {}
        start = time.monotonic()

        def _target() -> None:
            try:
                result["output"] = runner()
            except Exception as exc:  # pragma: no cover - runtime safety
                error["exc"] = exc
            finally:
                done.set()

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()

        while not done.wait(timeout=self.execution_heartbeat_seconds):
            elapsed = int(time.monotonic() - start)
            msg = f"⏳ Still working ({phase}) — {elapsed}s elapsed."
            self._safe_send(sender, msg)
            self._create_event(
                run_id=run_id,
                step=step,
                event_type="heartbeat",
                payload={"phase": phase, "elapsed_seconds": elapsed},
            )

        if "exc" in error:
            raise error["exc"]

        return result.get("output", "")

    def _handle_post_execution_cleanup(self, source_context: dict[str, Any], result: str) -> None:
        channel = source_context.get("channel")

        try:
            if channel == "reminders" and self.reminders_egress:
                reminder_id = source_context.get("reminder_id")
                list_name = source_context.get("list_name")
                if reminder_id and list_name:
                    self.reminders_egress.move_to_archive(
                        reminder_id=reminder_id,
                        result_text=f"[Apple Flow Result]\n\n{result}",
                        source_list_name=list_name,
                        archive_list_name=self.reminders_archive_list_name,
                    )

            elif channel == "notes" and self.notes_egress:
                note_id = source_context.get("note_id")
                folder_name = source_context.get("folder_name")
                if note_id and folder_name and hasattr(self.notes_egress, "move_to_archive"):
                    self.notes_egress.move_to_archive(
                        note_id=note_id,
                        result_text=f"[Apple Flow Result]\n\n{result}",
                        source_folder_name=folder_name,
                        archive_subfolder_name=self.notes_archive_folder_name,
                    )

            elif channel == "calendar" and self.calendar_egress:
                event_id = source_context.get("event_id")
                if event_id and hasattr(self.calendar_egress, "annotate_event"):
                    self.calendar_egress.annotate_event(event_id, f"\n\n[Apple Flow Result]\n{result}")
        except Exception as exc:
            logger.warning("Post-execution cleanup failed for channel=%s: %s", channel, exc)

    def _log(self, kind: str, sender: str, request: str, response: str) -> None:
        log_to_notes(self.log_notes_egress, self.notes_log_folder_name, kind, sender, request, response)

    def _create_event(self, run_id: str, step: str, event_type: str, payload: dict[str, Any]) -> None:
        if hasattr(self.store, "create_event"):
            self.store.create_event(
                event_id=f"evt_{uuid4().hex[:12]}",
                run_id=run_id,
                step=step,
                event_type=event_type,
                payload=payload,
            )

    def _safe_send(self, recipient: str, text: str) -> bool:
        try:
            self.egress.send(recipient, text)
            return True
        except Exception as exc:  # pragma: no cover - runtime safety
            logger.error("Failed to send outbound message to %s: %s", recipient, exc)
            return False

    def _next_attempt(self, run_id: str) -> int:
        if hasattr(self.store, "count_run_events"):
            return int(self.store.count_run_events(run_id, event_type="execution_started")) + 1

        if hasattr(self.store, "list_events_for_run"):
            events = self.store.list_events_for_run(run_id, limit=200)
        elif hasattr(self.store, "list_events"):
            events = [e for e in self.store.list_events(limit=500) if e.get("run_id") == run_id]
        else:
            events = []
        started = [e for e in events if e.get("event_type") == "execution_started"]
        return len(started) + 1

    def _classify_execution_outcome(self, output: str) -> tuple[str, str]:
        text = (output or "").strip()
        lower = text.lower()
        if "timed out" in lower:
            return "timeout", "connector timeout"
        if lower.startswith("blocker:") or "requires your input" in lower or "need your input" in lower:
            return "blocked", "user input required"
        if lower.startswith("error:"):
            return "error", "connector error"
        if not text:
            return "error", "empty output"
        return "success", "ok"

    def _should_checkpoint(self, outcome: str, attempt: int) -> bool:
        if attempt >= self.max_resume_attempts:
            return False
        if outcome == "blocked":
            return True
        if outcome == "timeout" and self.checkpoint_on_timeout:
            return True
        return False

    def _checkpoint_run(
        self,
        sender: str,
        run_id: str,
        attempt: int,
        reason: str,
        output: str,
        approval_sender: str,
        previous_request_id: str,
    ) -> tuple[str, str]:
        self.store.update_run_state(run_id, RunState.AWAITING_APPROVAL.value)
        checkpoint_request_id = f"req_{uuid4().hex[:8]}"
        expires_at = (datetime.now(UTC) + timedelta(minutes=self.approval_ttl_minutes)).isoformat()
        preview = (
            f"Checkpoint after attempt {attempt}/{self.max_resume_attempts} ({reason}).\n"
            f"Last output:\n{output[:700]}"
        )
        self.store.create_approval(
            request_id=checkpoint_request_id,
            run_id=run_id,
            summary="checkpoint re-approval required",
            command_preview=preview,
            expires_at=expires_at,
            sender=approval_sender,
        )
        self._create_event(
            run_id=run_id,
            step="executor",
            event_type="checkpoint_created",
            payload={
                "previous_request_id": previous_request_id,
                "checkpoint_request_id": checkpoint_request_id,
                "attempt": attempt,
                "reason": reason,
            },
        )

        message = (
            f"⚠️ I paused at a checkpoint ({reason}) after attempt {attempt}/{self.max_resume_attempts}.\n\n"
            f"Reply `approve {checkpoint_request_id}` to continue.\n"
            f"You can also add guidance:\n"
            f"`approve {checkpoint_request_id} <extra instructions>`\n\n"
            f"Or cancel with `deny {checkpoint_request_id}`."
        )
        self._safe_send(sender, message)
        return message, checkpoint_request_id

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
