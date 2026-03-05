"""Approval workflow handler — extracted from orchestrator.py."""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .commanding import CommandKind, extract_prompt_labels
from .models import InboundMessage, RunState
from .notes_logging import log_to_notes
from .protocols import ConnectorProtocol, EgressProtocol, StoreProtocol
from .utils import normalize_sender

if TYPE_CHECKING:
    from .run_executor import RunExecutor
    from .scheduler import FollowUpScheduler

logger = logging.getLogger("apple_flow.approval")
_CALL_ME_RE = re.compile(r"^\s*call\s+me(?:\s+and\s+say\s+(?P<say>.+))?\s*$", re.IGNORECASE | re.DOTALL)


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
        auto_resume_on_timeout: bool,
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
        run_executor: RunExecutor | None = None,
        approval_sender_override: str = "",
        phone_owner_number: str = "",
        phone_preferred_app: str = "phone",
        phone_tts_voice: str = "",
        phone_tts_rate: float = 180.0,
        phone_tts_engine: str = "auto",
        phone_piper_command: str = "piper",
        phone_piper_model_path: str = "",
        phone_in_call_tts_delay_seconds: float = 4.0,
        phone_enable_in_call_tts: bool = True,
        phone_deterministic_in_call_audio: bool = False,
        phone_virtual_audio_input_device: str = "BlackHole 2ch",
        phone_virtual_audio_output_device: str = "BlackHole 2ch",
        phone_audio_switch_command: str = "SwitchAudioSource",
        phone_audio_play_command: str = "afplay",
        phone_audio_route_settle_seconds: float = 0.8,
    ) -> None:
        self.connector = connector
        self.egress = egress
        self.store = store
        self.approval_ttl_minutes = approval_ttl_minutes
        self.enable_progress_streaming = enable_progress_streaming
        self.progress_update_interval_seconds = progress_update_interval_seconds
        self.execution_heartbeat_seconds = max(5.0, execution_heartbeat_seconds)
        self.checkpoint_on_timeout = checkpoint_on_timeout
        self.auto_resume_on_timeout = auto_resume_on_timeout
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
        self.run_executor = run_executor
        self.approval_sender_override = approval_sender_override
        self.phone_owner_number = (phone_owner_number or "").strip()
        self.phone_preferred_app = (phone_preferred_app or "phone").strip().lower()
        self.phone_tts_voice = phone_tts_voice or ""
        self.phone_tts_rate = float(phone_tts_rate)
        self.phone_tts_engine = (phone_tts_engine or "auto").strip().lower()
        self.phone_piper_command = phone_piper_command or "piper"
        self.phone_piper_model_path = phone_piper_model_path or ""
        self.phone_in_call_tts_delay_seconds = float(phone_in_call_tts_delay_seconds)
        self.phone_enable_in_call_tts = bool(phone_enable_in_call_tts)
        self.phone_deterministic_in_call_audio = bool(phone_deterministic_in_call_audio)
        self.phone_virtual_audio_input_device = phone_virtual_audio_input_device or "BlackHole 2ch"
        self.phone_virtual_audio_output_device = phone_virtual_audio_output_device or "BlackHole 2ch"
        self.phone_audio_switch_command = phone_audio_switch_command or "SwitchAudioSource"
        self.phone_audio_play_command = phone_audio_play_command or "afplay"
        self.phone_audio_route_settle_seconds = float(phone_audio_route_settle_seconds)

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
        next_state = RunState.QUEUED.value if self.run_executor is not None else RunState.EXECUTING.value
        self.store.update_run_state(approval["run_id"], next_state)
        self._create_event(
            run_id=approval["run_id"],
            step="approval",
            event_type="approved",
            payload={"request_id": request_id, "mode": "async" if self.run_executor is not None else "inline"},
        )
        run = self.store.get_run(approval["run_id"])
        if run is None:
            response = f"Request {request_id} approved, but run was not found."
            self._safe_send(sender, response)
            return OrchestrationResult(kind=kind, response=response)

        source_context = self.store.get_run_source_context(approval["run_id"]) or {}
        egress_context = self._egress_context_from_source_context(source_context)
        self._notify_source_channel_approval(
            source_context=source_context,
            request_id=request_id,
            run_id=approval["run_id"],
        )

        attempt = self._next_attempt(approval["run_id"])
        if self.run_executor is not None:
            self.run_executor.enqueue(
                run_id=approval["run_id"],
                sender=sender,
                request_id=request_id,
                attempt=attempt,
                extra_instructions=extra_instructions,
                approval_sender=approval.get("sender", sender),
                plan_summary=approval.get("command_preview", ""),
            )
            queued = (
                f"✅ Approved {request_id}. Queued execution "
                f"(run `{approval['run_id']}`, attempt {attempt}/{self.max_resume_attempts}). "
                f"Send `status {approval['run_id']}` for progress."
            )
            self._safe_send(sender, queued, context=egress_context)
            self._log(kind.value, sender, run.get("intent", ""), queued)
            return OrchestrationResult(kind=kind, run_id=approval["run_id"], response=queued)

        return self._execute_run_attempt(
            kind=kind,
            sender=sender,
            run=run,
            run_id=approval["run_id"],
            request_id=request_id,
            attempt=attempt,
            extra_instructions=extra_instructions,
            plan_summary=approval.get("command_preview", ""),
            approval_sender=approval.get("sender", sender),
        )

    def execute_queued_run(
        self,
        *,
        run_id: str,
        sender: str,
        request_id: str,
        attempt: int,
        extra_instructions: str,
        plan_summary: str,
        approval_sender: str,
    ) -> OrchestrationResult:
        """Execute a previously approved run in background worker mode."""
        run = self.store.get_run(run_id)
        if run is None:
            response = f"Run `{run_id}` not found."
            return OrchestrationResult(kind=CommandKind.TASK, run_id=run_id, response=response)
        kind = CommandKind.PROJECT if run.get("intent") == CommandKind.PROJECT.value else CommandKind.TASK
        self.store.update_run_state(run_id, RunState.EXECUTING.value)
        return self._execute_run_attempt(
            kind=kind,
            sender=sender,
            run=run,
            run_id=run_id,
            request_id=request_id,
            attempt=attempt,
            extra_instructions=extra_instructions,
            plan_summary=plan_summary,
            approval_sender=approval_sender,
            send_started=False,
        )

    def _execute_run_attempt(
        self,
        *,
        kind: CommandKind,
        sender: str,
        run: dict[str, Any],
        run_id: str,
        request_id: str,
        attempt: int,
        extra_instructions: str,
        plan_summary: str,
        approval_sender: str,
        send_started: bool = True,
    ) -> OrchestrationResult:
        self._create_event(
            run_id=run_id,
            step="executor",
            event_type="execution_started",
            payload={"request_id": request_id, "attempt": attempt},
        )
        run_request_text = self._get_run_request_text(run_id) or str(run.get("intent", ""))
        source_context = self.store.get_run_source_context(run_id) or {}
        egress_context = self._egress_context_from_source_context(source_context)
        if send_started:
            self._safe_send(
                sender,
                (
                    f"✅ Approved {request_id}. Starting execution "
                    f"(run `{run_id}`, attempt {attempt}/{self.max_resume_attempts})."
                ),
                context=egress_context,
            )

        phone_action = self._extract_phone_call_action(source_context)
        if phone_action is not None:
            return self._execute_phone_call_action(
                kind=kind,
                sender=sender,
                run_id=run_id,
                request_id=request_id,
                attempt=attempt,
                extra_instructions=extra_instructions,
                run_request_text=run_request_text,
                phone_action=phone_action,
                egress_context=egress_context,
            )

        thread_id = self.connector.get_or_create_thread(sender)
        team_context = None
        if isinstance(source_context, dict):
            maybe_team = source_context.get("team_context")
            if isinstance(maybe_team, dict):
                team_context = maybe_team

        exec_prompt_parts = [
            "executor mode: perform the approved plan carefully and provide concise progress + final output.",
            "If blocked on input/credentials/decision, prefix your response with `BLOCKER:` and ask one clear question.",
            f"workspace={run['cwd']}",
        ]
        requested_labels = extract_prompt_labels(self._get_run_request_text(run_id))
        if requested_labels:
            exec_prompt_parts.append(
                "When triaging Apple Mail, only use these labels: "
                + ", ".join(requested_labels)
                + "."
            )
        if plan_summary:
            exec_prompt_parts.append(f"approved plan:\n{plan_summary}")
        if extra_instructions:
            exec_prompt_parts.append(f"additional instructions from user: {extra_instructions}")
        attachment_prompt_block = ""
        if isinstance(source_context, dict):
            attachment_prompt_block = str(source_context.get("attachment_prompt_block") or "").strip()
        if attachment_prompt_block:
            exec_prompt_parts.append(attachment_prompt_block)
        exec_prompt = "\n".join(exec_prompt_parts)
        exec_prompt = self._apply_team_prompt_fallback(exec_prompt, team_context)

        execution_output = self._run_execution(
            sender=sender,
            thread_id=thread_id,
            prompt=exec_prompt,
            run_id=run_id,
            step="executor",
            phase=f"execution attempt {attempt}",
            team_context=team_context,
            egress_context=egress_context,
            allow_tools=True,
            cwd=str(run.get("cwd", "")),
        )

        outcome, reason = self._classify_execution_outcome(execution_output)
        should_checkpoint = self._should_checkpoint(outcome=outcome, attempt=attempt)
        if should_checkpoint:
            checkpoint_message, checkpoint_request_id = self._checkpoint_run(
                sender=sender,
                run_id=run_id,
                attempt=attempt,
                reason=reason,
                output=execution_output,
                approval_sender=approval_sender,
                previous_request_id=request_id,
                egress_context=egress_context,
            )
            self._log(kind.value, sender, run_request_text, checkpoint_message)
            return OrchestrationResult(
                kind=kind,
                run_id=run_id,
                approval_request_id=checkpoint_request_id,
                response=checkpoint_message,
            )

        self._create_event(
            run_id=run_id,
            step="executor",
            event_type="completed" if outcome == "success" else "execution_failed",
            payload={"reason": reason, "snippet": execution_output[:200]},
        )

        if outcome != "success":
            self.store.update_run_state(run_id, RunState.FAILED.value)
            final = f"❌ Execution failed ({reason}).\n\n{execution_output}"
            self._safe_send(sender, final, context=egress_context)
            self._log(kind.value, sender, run_request_text, final)
            return OrchestrationResult(kind=kind, run_id=run_id, response=final)

        if self.enable_verifier:
            self.store.update_run_state(run_id, RunState.VERIFYING.value)
            verify_prompt = "verifier mode: validate completion evidence and summarize pass/fail with key checks."
            verify_prompt = self._apply_team_prompt_fallback(verify_prompt, team_context)
            verification_output = self._run_execution(
                sender=sender,
                thread_id=thread_id,
                prompt=verify_prompt,
                run_id=run_id,
                step="verifier",
                phase=f"verification attempt {attempt}",
                team_context=team_context,
                egress_context=egress_context,
                allow_tools=False,
            )
            verifier_outcome, verifier_reason = self._classify_execution_outcome(verification_output)
            self._create_event(
                run_id=run_id,
                step="verifier",
                event_type="completed" if verifier_outcome == "success" else "execution_failed",
                payload={"reason": verifier_reason, "snippet": verification_output[:200]},
            )
            if verifier_outcome != "success":
                self.store.update_run_state(run_id, RunState.FAILED.value)
                final = (
                    f"❌ Verification failed ({verifier_reason}).\n\n"
                    f"Execution:\n{execution_output}\n\nVerification:\n{verification_output}"
                )
                self._safe_send(sender, final, context=egress_context)
                self._log(kind.value, sender, run_request_text, final)
                return OrchestrationResult(kind=kind, run_id=run_id, response=final)
            final = f"Execution:\n{execution_output}\n\nVerification:\n{verification_output}"
        else:
            final = execution_output

        self.store.update_run_state(run_id, RunState.COMPLETED.value)
        self._safe_send(sender, final, context=egress_context)
        self._log(kind.value, sender, run_request_text, final)

        if source_context:
            self._handle_post_execution_cleanup(source_context, final)

        if self.scheduler:
            try:
                self.scheduler.schedule(
                    run_id=run_id,
                    sender=sender,
                    action_type="follow_up",
                    payload={"summary": f"Follow up on approved task {request_id}"},
                )
            except Exception as exc:
                logger.debug("Failed to schedule follow-up: %s", exc)

        return OrchestrationResult(kind=kind, run_id=run_id, response=final)

    def handle_approval_required(
        self,
        message: InboundMessage,
        kind: CommandKind,
        thread_id: str,
        payload: str,
        workspace: str,
        default_workspace: str,
        is_workspace_allowed: Any,
        team_context: dict[str, Any] | None = None,
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

        phone_action = self._parse_phone_call_me_request(kind=kind, payload=payload)
        if phone_action is not None and not self.phone_owner_number:
            response = (
                "Phone callback is not configured. Set `apple_flow_phone_owner_number` "
                "in your .env to use `task: call me`."
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
            elif channel == "mail":
                source_context = {
                    "channel": "mail",
                    "mail_message_id": message.context.get("mail_message_id"),
                    "mail_subject": message.context.get("mail_subject"),
                    "mail_subject_raw": message.context.get("mail_subject_raw"),
                    "mail_subject_sanitized": message.context.get("mail_subject_sanitized"),
                }
        if phone_action is not None:
            if source_context is None:
                source_context = {}
            source_context["channel"] = "phone"
            source_context["phone_action"] = phone_action
        if team_context:
            if source_context is None:
                source_context = {}
            source_context["team_context"] = team_context
        attachment_prompt_block = str(message.context.get("attachment_prompt_block") or "").strip()
        if attachment_prompt_block:
            if source_context is None:
                source_context = {}
            source_context["attachment_prompt_block"] = attachment_prompt_block

        self.store.create_run(
            run_id=run_id,
            sender=message.sender,
            intent=kind.value,
            state=RunState.PLANNING.value,
            cwd=ws,
            risk_level="execute",
            source_context=source_context,
        )
        self._create_event(
            run_id=run_id,
            step="request",
            event_type="request_received",
            payload={"request": payload, "intent": kind.value},
        )

        if phone_action is not None:
            plan_output = self._build_phone_call_plan(phone_action=phone_action, workspace=ws)
        else:
            planner_prompt = (
                "planner mode: produce an objective, steps, risks, and done criteria. "
                f"intent={kind.value}; request={payload}; workspace={ws}"
            )
            if attachment_prompt_block:
                planner_prompt = f"{planner_prompt}\n\n{attachment_prompt_block}"
            plan_output = self._run_connector_turn(
                thread_id=thread_id,
                prompt=self._apply_team_prompt_fallback(planner_prompt, team_context),
                team_context=team_context,
                allow_tools=False,
            )

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
        self._safe_send(message.sender, outbound, context=message.context)
        self._log(kind.value, message.sender, payload, outbound)
        return OrchestrationResult(kind=kind, run_id=run_id, approval_request_id=request_id, response=outbound)

    def _parse_phone_call_me_request(self, *, kind: CommandKind, payload: str) -> dict[str, Any] | None:
        if kind is not CommandKind.TASK:
            return None
        text = (payload or "").strip()
        if not text:
            return None
        match = _CALL_ME_RE.match(text)
        if not match:
            return None
        in_call_text = str(match.group("say") or "").strip()
        return {
            "action": "call_me",
            "request_text": text,
            "preflight_text": "Starting call now.",
            "in_call_text": in_call_text,
        }

    def _build_phone_call_plan(self, *, phone_action: dict[str, Any], workspace: str) -> str:
        in_call_text = str(phone_action.get("in_call_text") or "").strip()
        in_call_line = (
            f"- in-call TTS: {in_call_text}"
            if in_call_text
            else "- in-call TTS: skipped (no `and say ...` text provided)"
        )
        return "\n".join(
            [
                "Phone call plan (local-assisted):",
                f"- workspace: {workspace}",
                f"- target number: configured owner (`{self.phone_owner_number or '(unset)'}`)",
                f"- call app preference: {self.phone_preferred_app}",
                "- preflight TTS: \"Starting call now.\"",
                in_call_line,
                f"- in-call delay: {self.phone_in_call_tts_delay_seconds:.1f}s",
                f"- deterministic in-call audio: {'enabled' if self.phone_deterministic_in_call_audio else 'disabled'}",
                f"- TTS engine: {self.phone_tts_engine}",
                "",
                "Risks:",
                "- macOS may still show a system prompt for call launch.",
                (
                    "- deterministic mode hard-fails if virtual audio routing is unavailable."
                    if self.phone_deterministic_in_call_audio
                    else "- voicemail delivery is best-effort (not guaranteed)."
                ),
            ]
        )

    @staticmethod
    def _extract_phone_call_action(source_context: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(source_context, dict):
            return None
        phone_action = source_context.get("phone_action")
        if not isinstance(phone_action, dict):
            return None
        if str(phone_action.get("action", "")) != "call_me":
            return None
        return phone_action

    def _execute_phone_call_action(
        self,
        *,
        kind: CommandKind,
        sender: str,
        run_id: str,
        request_id: str,
        attempt: int,
        extra_instructions: str,
        run_request_text: str,
        phone_action: dict[str, Any],
        egress_context: dict[str, Any] | None,
    ) -> OrchestrationResult:
        from .apple_tools import phone_call_me

        in_call_text = str(phone_action.get("in_call_text") or "").strip()
        extra = (extra_instructions or "").strip()
        if extra:
            in_call_text = f"{in_call_text}\n{extra}".strip() if in_call_text else extra

        try:
            result = phone_call_me(
                owner_number=self.phone_owner_number,
                preflight_text=str(phone_action.get("preflight_text") or "").strip(),
                in_call_text=in_call_text,
                preferred_app=self.phone_preferred_app,
                voice=self.phone_tts_voice,
                rate=self.phone_tts_rate,
                tts_engine=self.phone_tts_engine,
                piper_command=self.phone_piper_command,
                piper_model_path=self.phone_piper_model_path,
                in_call_delay_seconds=self.phone_in_call_tts_delay_seconds,
                enable_in_call_tts=self.phone_enable_in_call_tts,
                deterministic_audio=self.phone_deterministic_in_call_audio,
                virtual_audio_input_device=self.phone_virtual_audio_input_device,
                virtual_audio_output_device=self.phone_virtual_audio_output_device,
                audio_switch_command=self.phone_audio_switch_command,
                audio_play_command=self.phone_audio_play_command,
                audio_route_settle_seconds=self.phone_audio_route_settle_seconds,
            )
        except Exception as exc:  # pragma: no cover - runtime safety
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        if not result.get("ok"):
            self.store.update_run_state(run_id, RunState.FAILED.value)
            reason = str(result.get("error", "phone action failed"))
            self._create_event(
                run_id=run_id,
                step="executor",
                event_type="execution_failed",
                payload={
                    "request_id": request_id,
                    "attempt": attempt,
                    "reason": reason,
                    "channel": "phone",
                },
            )
            final = f"❌ Phone callback failed ({reason})."
            self._safe_send(sender, final, context=egress_context)
            self._log(kind.value, sender, run_request_text, final)
            return OrchestrationResult(kind=kind, run_id=run_id, response=final)

        call_meta = result.get("call", {}) if isinstance(result.get("call"), dict) else {}
        warnings = result.get("warnings", []) if isinstance(result.get("warnings"), list) else []
        summary_lines = [
            "✅ Phone callback launched.",
            f"- number: {result.get('number') or self.phone_owner_number}",
            f"- call URI: {call_meta.get('uri', 'unknown')}",
            f"- app: {call_meta.get('app', self.phone_preferred_app)}",
            f"- deterministic audio: {'yes' if self.phone_deterministic_in_call_audio else 'no'}",
        ]
        if call_meta.get("fallback_used"):
            summary_lines.append("- fallback: used FaceTime Audio URL")
        if warnings:
            summary_lines.append("- warnings: " + ", ".join(str(item) for item in warnings))
        final = "\n".join(summary_lines)

        self.store.update_run_state(run_id, RunState.COMPLETED.value)
        self._create_event(
            run_id=run_id,
            step="executor",
            event_type="completed",
            payload={
                "request_id": request_id,
                "attempt": attempt,
                "channel": "phone",
                "call_uri": call_meta.get("uri", ""),
                "warnings": warnings,
                "deterministic_audio": self.phone_deterministic_in_call_audio,
            },
        )
        self._safe_send(sender, final, context=egress_context)
        self._log(kind.value, sender, run_request_text, final)

        if self.scheduler:
            try:
                self.scheduler.schedule(
                    run_id=run_id,
                    sender=sender,
                    action_type="follow_up",
                    payload={"summary": f"Follow up on approved task {request_id}"},
                )
            except Exception as exc:
                logger.debug("Failed to schedule follow-up: %s", exc)

        return OrchestrationResult(kind=kind, run_id=run_id, response=final)

    # --- Internal helpers ---

    def _run_connector_turn(
        self,
        thread_id: str,
        prompt: str,
        team_context: dict[str, Any] | None = None,
        *,
        allow_tools: bool = False,
        cwd: str | None = None,
    ) -> str:
        options: dict[str, Any] = {}
        if team_context and team_context.get("codex_config_path"):
            options["codex_config_path"] = team_context["codex_config_path"]
        if allow_tools:
            options["allow_tools"] = True
        if cwd and allow_tools:
            options["cwd"] = cwd
        if options:
            try:
                return self.connector.run_turn(thread_id, prompt, options=options)  # type: ignore[arg-type]
            except TypeError:
                pass
        return self.connector.run_turn(thread_id, prompt)

    def _run_connector_turn_streaming(
        self,
        thread_id: str,
        prompt: str,
        on_progress: Any,
        team_context: dict[str, Any] | None = None,
        *,
        allow_tools: bool = False,
        cwd: str | None = None,
    ) -> str:
        options: dict[str, Any] = {}
        if team_context and team_context.get("codex_config_path"):
            options["codex_config_path"] = team_context["codex_config_path"]
        if allow_tools:
            options["allow_tools"] = True
        if cwd and allow_tools:
            options["cwd"] = cwd
        if options:
            try:
                return self.connector.run_turn_streaming(
                    thread_id,
                    prompt,
                    on_progress,
                    options=options,
                )  # type: ignore[arg-type]
            except TypeError:
                pass
        return self.connector.run_turn_streaming(thread_id, prompt, on_progress)

    def _apply_team_prompt_fallback(self, prompt: str, team_context: dict[str, Any] | None) -> str:
        if not team_context:
            return prompt
        fallback = str(team_context.get("prompt_fallback", "")).strip()
        if not fallback:
            return prompt
        return f"{fallback}\n\n{prompt}"

    def _run_execution(
        self,
        sender: str,
        thread_id: str,
        prompt: str,
        run_id: str,
        step: str,
        phase: str,
        team_context: dict[str, Any] | None = None,
        egress_context: dict[str, Any] | None = None,
        *,
        allow_tools: bool = False,
        cwd: str | None = None,
    ) -> str:
        started_at = time.monotonic()
        connector_name = type(self.connector).__name__
        self._create_event(
            run_id=run_id,
            step=step,
            event_type="connector_started",
            payload={"phase": phase, "connector": connector_name},
        )
        try:
            if self.enable_progress_streaming and hasattr(self.connector, "run_turn_streaming"):
                output = self._run_with_progress(
                    sender,
                    thread_id,
                    prompt,
                    run_id=run_id,
                    step=step,
                    phase=phase,
                    team_context=team_context,
                    egress_context=egress_context,
                    allow_tools=allow_tools,
                    cwd=cwd,
                )
            else:
                output = self._run_with_heartbeat(
                    sender=sender,
                    runner=lambda: self._run_connector_turn(
                        thread_id,
                        prompt,
                        team_context,
                        allow_tools=allow_tools,
                        cwd=cwd,
                    ),
                    run_id=run_id,
                    step=step,
                    phase=phase,
                    egress_context=egress_context,
                )
            duration_ms = int((time.monotonic() - started_at) * 1000)
            self._create_event(
                run_id=run_id,
                step=step,
                event_type="connector_completed",
                payload={
                    "phase": phase,
                    "connector": connector_name,
                    "duration_ms": duration_ms,
                    "snippet": output[:200],
                    "status": "completed",
                },
            )
            return output
        except Exception as exc:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            self._create_event(
                run_id=run_id,
                step=step,
                event_type="connector_failed",
                payload={
                    "phase": phase,
                    "connector": connector_name,
                    "duration_ms": duration_ms,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "status": "failed",
                },
            )
            raise

    def _get_run_request_text(self, run_id: str) -> str:
        """Best-effort retrieval of the original task/project request text."""
        if not hasattr(self.store, "list_events_for_run"):
            return ""
        try:
            events = self.store.list_events_for_run(run_id, limit=50)
        except Exception:
            return ""

        for event in events:
            if event.get("event_type") != "request_received":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            request = payload.get("request")
            if isinstance(request, str):
                return request
        return ""

    def _run_with_progress(
        self,
        sender: str,
        thread_id: str,
        prompt: str,
        run_id: str,
        step: str,
        phase: str,
        team_context: dict[str, Any] | None = None,
        egress_context: dict[str, Any] | None = None,
        *,
        allow_tools: bool = False,
        cwd: str | None = None,
    ) -> str:
        last_update = 0.0
        progress_state: dict[str, Any] = {
            "last_output_monotonic": None,
            "last_snippet": "",
        }

        def on_progress(line: str) -> None:
            nonlocal last_update
            now = time.monotonic()
            preview = line.strip()[:200]
            if preview:
                progress_state["last_output_monotonic"] = now
                progress_state["last_snippet"] = preview

            if (now - last_update) >= self.progress_update_interval_seconds:
                if preview:
                    self._safe_send(sender, f"[Progress] {preview}", context=egress_context)
                    self._create_event(
                        run_id=run_id,
                        step=step,
                        event_type="progress",
                        payload={"phase": phase, "snippet": preview},
                    )
                last_update = now

        return self._run_with_heartbeat(
            sender=sender,
            runner=lambda: self._run_connector_turn_streaming(
                thread_id,
                prompt,
                on_progress,
                team_context,
                allow_tools=allow_tools,
                cwd=cwd,
            ),
            run_id=run_id,
            step=step,
            phase=phase,
            progress_state=progress_state,
            egress_context=egress_context,
        )

    def _run_with_heartbeat(
        self,
        sender: str,
        runner: Any,
        run_id: str,
        step: str,
        phase: str,
        progress_state: dict[str, Any] | None = None,
        egress_context: dict[str, Any] | None = None,
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
            now = time.monotonic()
            elapsed = int(now - start)
            payload: dict[str, Any] = {"phase": phase, "elapsed_seconds": elapsed}
            detail = "no streamed output yet"

            if progress_state:
                last_output = progress_state.get("last_output_monotonic")
                last_snippet = str(progress_state.get("last_snippet") or "")
                if isinstance(last_output, (int, float)):
                    stale_for = max(0, int(now - float(last_output)))
                    payload["no_output_seconds"] = stale_for
                    if last_snippet:
                        detail = f"last output {stale_for}s ago: {last_snippet}"
                        payload["last_snippet"] = last_snippet
                else:
                    payload["no_output_seconds"] = elapsed

            msg = f"⏳ Still working ({phase}) — {elapsed}s elapsed; {detail}."
            self._safe_send(sender, msg, context=egress_context)
            self._create_event(
                run_id=run_id,
                step=step,
                event_type="heartbeat",
                payload=payload,
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

    def _notify_source_channel_approval(
        self,
        *,
        source_context: dict[str, Any],
        request_id: str,
        run_id: str,
    ) -> None:
        channel = source_context.get("channel")
        if channel != "notes" or not self.notes_egress:
            return

        msg = (
            f"[Apple Flow] ✅ Approved in iMessage ({request_id}). "
            f"Execution started for run {run_id}."
        )

        try:
            note_id = source_context.get("note_id")
            if note_id and hasattr(self.notes_egress, "append_result"):
                self.notes_egress.append_result(note_id, msg)
        except Exception as exc:
            logger.warning("Failed to write approval breadcrumb for channel=%s: %s", channel, exc)

    def _log(self, kind: str, sender: str, request: str, response: str) -> None:
        log_to_notes(self.log_notes_egress, self.notes_log_folder_name, kind, sender, request, response)

    def _create_event(self, run_id: str, step: str, event_type: str, payload: dict[str, Any]) -> None:
        if hasattr(self.store, "create_event"):
            event_payload = dict(payload or {})
            source_context = self.store.get_run_source_context(run_id) if hasattr(self.store, "get_run_source_context") else {}
            run = self.store.get_run(run_id) if hasattr(self.store, "get_run") else {}
            if isinstance(source_context, dict):
                channel = source_context.get("channel")
                if channel and "channel" not in event_payload:
                    event_payload["channel"] = channel
            if isinstance(run, dict):
                sender = run.get("sender")
                workspace = run.get("cwd")
                if sender and "sender" not in event_payload:
                    event_payload["sender"] = sender
                if workspace and "workspace" not in event_payload:
                    event_payload["workspace"] = workspace
            self.store.create_event(
                event_id=f"evt_{uuid4().hex[:12]}",
                run_id=run_id,
                step=step,
                event_type=event_type,
                payload=event_payload,
            )

    def _safe_send(
        self,
        recipient: str,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        try:
            self.egress.send(recipient, text, context=context)
            return True
        except TypeError:
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
        if self._is_placeholder_output(text):
            return "placeholder", "placeholder output"
        if not text:
            return "error", "empty output"
        return "success", "ok"

    def _should_checkpoint(self, outcome: str, attempt: int) -> bool:
        if attempt >= self.max_resume_attempts:
            return False
        if outcome == "blocked":
            return True
        if outcome == "placeholder":
            return True
        if outcome == "timeout" and (self.checkpoint_on_timeout and not self.auto_resume_on_timeout):
            return True
        return False

    @staticmethod
    def _is_placeholder_output(text: str) -> bool:
        normalized = (text or "").strip().lower().rstrip(".")
        return normalized in {"no response generated", "follow-on request executed"}

    def _checkpoint_run(
        self,
        sender: str,
        run_id: str,
        attempt: int,
        reason: str,
        output: str,
        approval_sender: str,
        previous_request_id: str,
        egress_context: dict[str, Any] | None = None,
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
        self._safe_send(sender, message, context=egress_context)
        return message, checkpoint_request_id

    @staticmethod
    def _egress_context_from_source_context(source_context: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(source_context, dict):
            return None
        if source_context.get("channel") != "mail":
            return None
        return {
            "channel": "mail",
            "mail_message_id": source_context.get("mail_message_id"),
            "mail_subject": source_context.get("mail_subject"),
            "mail_subject_raw": source_context.get("mail_subject_raw"),
            "mail_subject_sanitized": source_context.get("mail_subject_sanitized"),
        }

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
