from __future__ import annotations

import html as _html_mod
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger("apple_flow.orchestrator")

from .commanding import CommandKind, ParsedCommand, is_likely_mutating, parse_command
from .models import InboundMessage, RunState
from .protocols import ConnectorProtocol, EgressProtocol, StoreProtocol

_SEP = "━" * 30


def _inline_md(text: str) -> str:
    """Convert inline markdown spans to HTML (bold, italic, code, links)."""
    text = _html_mod.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _md_to_html(text: str) -> str:
    """Convert a markdown string to HTML suitable for Apple Notes body."""
    lines = text.split("\n")
    parts: list[str] = []
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            parts.append("</ul>")
            in_ul = False

    for line in lines:
        s = line.strip()
        if s in ("---", "***", "___"):
            close_ul()
            parts.append("<hr>")
        elif s.startswith("### "):
            close_ul()
            parts.append(f"<h3>{_inline_md(s[4:])}</h3>")
        elif s.startswith("## "):
            close_ul()
            parts.append(f"<h2>{_inline_md(s[3:])}</h2>")
        elif s.startswith("# "):
            close_ul()
            parts.append(f"<h1>{_inline_md(s[2:])}</h1>")
        elif s.startswith("- ") or s.startswith("* "):
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{_inline_md(s[2:])}</li>")
        elif not s:
            close_ul()
            parts.append("<br>")
        else:
            close_ul()
            parts.append(f"<p>{_inline_md(s)}</p>")

    close_ul()
    return "".join(parts)


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
        personality_prompt: str = "",
        reminders_egress: Any = None,
        reminders_archive_list_name: str = "Archive",
        notes_egress: Any = None,
        notes_archive_folder_name: str = "codex-archive",
        calendar_egress: Any = None,
        shutdown_callback: Callable[[], None] | None = None,
        log_notes_egress: Any = None,
        notes_log_folder_name: str = "codex-logs",
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
        self.personality_prompt = personality_prompt
        self.reminders_egress = reminders_egress
        self.reminders_archive_list_name = reminders_archive_list_name
        self.notes_egress = notes_egress
        self.notes_archive_folder_name = notes_archive_folder_name
        self.calendar_egress = calendar_egress
        self.shutdown_callback = shutdown_callback
        self.log_notes_egress = log_notes_egress
        self.notes_log_folder_name = notes_log_folder_name

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
        elif command.kind is CommandKind.CHAT and not self.require_chat_prefix:
            # Natural language mode: strip relay: prefix if present (optional graceful compat)
            if raw_text.lower().startswith(self.chat_prefix.lower()):
                stripped = raw_text[len(self.chat_prefix) :].strip()
                command = ParsedCommand(kind=CommandKind.CHAT, payload=stripped, workspace=command.workspace)

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

        if command.kind is CommandKind.SYSTEM:
            return self._handle_system(message.sender, command.payload)

        # Natural language mode: auto-promote bare CHAT messages with mutating intent to TASK
        if (
            command.kind is CommandKind.CHAT
            and not self.require_chat_prefix
            and is_likely_mutating(command.payload)
        ):
            command = ParsedCommand(kind=CommandKind.TASK, payload=command.payload, workspace=command.workspace)

        workspace = self._resolve_workspace(command.workspace)

        thread_id = self.connector.get_or_create_thread(message.sender)
        self.store.upsert_session(message.sender, thread_id, command.kind.value)

        if command.kind in {CommandKind.TASK, CommandKind.PROJECT}:
            return self._handle_approval_required_command(message, command.kind, thread_id, command.payload, workspace)

        prompt = self._build_non_mutating_prompt(command.kind, command.payload, workspace)
        prompt = self._inject_auto_context(message.sender, prompt)
        prompt = self._inject_attachment_context(message, prompt)

        response = self.connector.run_turn(thread_id, prompt)
        self.egress.send(message.sender, response)
        self._log_to_notes(command.kind.value, message.sender, command.payload, response)
        return OrchestrationResult(kind=command.kind, response=response)

    # --- Feature 2: Health Dashboard ---

    def _handle_health(self, sender: str) -> OrchestrationResult:
        parts = ["Apple Flow Health"]

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

    # --- System Command ---

    def _handle_system(self, sender: str, subcommand: str) -> OrchestrationResult:
        sub = subcommand.strip().lower()
        if sub == "stop":
            response = "Apple Flow shutting down..."
            self.egress.send(sender, response)
            if self.shutdown_callback is not None:
                self.shutdown_callback()
        elif sub == "restart":
            response = "Apple Flow restarting... (text 'health' to confirm it's back)"
            self.egress.send(sender, response)
            if self.shutdown_callback is not None:
                self.shutdown_callback()
        else:
            response = "Unknown system command. Use: system: stop  or  system: restart"
            self.egress.send(sender, response)
        return OrchestrationResult(kind=CommandKind.SYSTEM, response=sub)

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
        self._log_to_notes(kind.value, sender, run.get("intent", ""), final)

        # Post-execution cleanup: move reminders to archive, update notes, etc.
        source_context = self.store.get_run_source_context(approval["run_id"])
        if source_context:
            self._handle_post_execution_cleanup(source_context, final)

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

        # Extract source context for tracking the originating channel (reminders, notes, etc.)
        source_context = None
        if message.context:
            # Build source_context from message.context if present
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
            f"Here's my plan:\n{plan_output}\n\n"
            f"Reply `approve {request_id}` to proceed, or `deny {request_id}` to cancel."
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

    # --- Post-Execution Cleanup ---

    def _handle_post_execution_cleanup(self, source_context: dict[str, Any], result: str) -> None:
        """Handle cleanup after task execution (move reminders to archive, update notes, etc.)"""
        channel = source_context.get("channel")

        if channel == "reminders" and self.reminders_egress:
            reminder_id = source_context.get("reminder_id")
            list_name = source_context.get("list_name")
            if reminder_id and list_name:
                self.reminders_egress.move_to_archive(
                    reminder_id=reminder_id,
                    result_text=f"[Codex Result]\n\n{result}",
                    source_list_name=list_name,
                    archive_list_name=self.reminders_archive_list_name,
                )

        elif channel == "notes" and self.notes_egress:
            note_id = source_context.get("note_id")
            folder_name = source_context.get("folder_name")
            if note_id and folder_name and hasattr(self.notes_egress, "move_to_archive"):
                self.notes_egress.move_to_archive(
                    note_id=note_id,
                    result_text=f"[Codex Result]\n\n{result}",
                    source_folder_name=folder_name,
                    archive_subfolder_name=self.notes_archive_folder_name,
                )

        elif channel == "calendar" and self.calendar_egress:
            event_id = source_context.get("event_id")
            if event_id and hasattr(self.calendar_egress, "annotate_event"):
                self.calendar_egress.annotate_event(event_id, f"\n\n[Codex Result]\n{result}")

    def _log_to_notes(self, kind: str, sender: str, request: str, response: str) -> None:
        """Create a rich-HTML log note for a completed AI turn (fire-and-forget)."""
        if self.log_notes_egress is None:
            return
        try:
            now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            payload_preview = request[:50].replace("\n", " ")
            title = f"[{kind}] {payload_preview} — {now_str}"

            request_html = _md_to_html(request)
            response_html = _md_to_html(response)

            body = (
                f"<h1>Agent Log</h1>"
                f"<p><b>Command:</b> {_html_mod.escape(kind)}"
                f" &nbsp;|&nbsp; <b>Sender:</b> {_html_mod.escape(sender)}<br>"
                f"<b>Time:</b> {now_str}</p>"
                f"<hr>"
                f"<h2>Request</h2>"
                f"{request_html}"
                f"<hr>"
                f"<h2>Response</h2>"
                f"{response_html}"
            )

            self.log_notes_egress.create_log_note(
                folder_name=self.notes_log_folder_name,
                title=title,
                body=body,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to log to Notes: %s", exc)

    # --- Prompt Building ---

    def _build_unified_prompt(self, payload: str, workspace: str | None = None) -> str:
        """Return the user payload. Personality/system context is handled by the connector via --system."""
        return payload

    def _build_non_mutating_prompt(self, kind: CommandKind, payload: str, workspace: str | None = None) -> str:
        if kind is CommandKind.IDEA:
            return f"brainstorm mode: generate options, trade-offs, and recommendation. request={payload}"
        if kind is CommandKind.PLAN:
            return f"planning mode: create a stepwise implementation plan with acceptance criteria. goal={payload}"
        return self._build_unified_prompt(payload, workspace)

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
