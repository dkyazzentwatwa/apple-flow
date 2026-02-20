from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

logger = logging.getLogger("apple_flow.orchestrator")

from .approval import ApprovalHandler, OrchestrationResult
from .commanding import CommandKind, ParsedCommand, is_likely_mutating, parse_command
from .models import InboundMessage, RunState
from .notes_logging import log_to_notes
from .protocols import ConnectorProtocol, EgressProtocol, StoreProtocol

if TYPE_CHECKING:
    from .memory import FileMemory
    from .office_sync import OfficeSyncer
    from .scheduler import FollowUpScheduler

_SEP = "━" * 30
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


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
        enable_verifier: bool = False,
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
        memory: FileMemory | None = None,
        scheduler: FollowUpScheduler | None = None,
        office_syncer: OfficeSyncer | None = None,
        log_file_path: str | None = None,
    ):
        self.connector = connector
        self.egress = egress
        self.store = store
        self.allowed_workspaces = [str(Path(p).resolve()) for p in allowed_workspaces]
        self._allowed_workspace_set: frozenset[Path] = frozenset(
            Path(p) for p in self.allowed_workspaces
        )
        self.default_workspace = str(Path(default_workspace).resolve())
        self.require_chat_prefix = require_chat_prefix
        self.chat_prefix = (chat_prefix or "relay:").strip()
        self.workspace_aliases = workspace_aliases or {}
        self.auto_context_messages = auto_context_messages
        self.enable_attachments = enable_attachments
        self.personality_prompt = personality_prompt
        self.shutdown_callback = shutdown_callback
        self.log_notes_egress = log_notes_egress
        self.notes_log_folder_name = notes_log_folder_name
        self.memory = memory
        self.office_syncer = office_syncer
        self.log_file_path = log_file_path

        self._approval = ApprovalHandler(
            connector=connector,
            egress=egress,
            store=store,
            approval_ttl_minutes=approval_ttl_minutes,
            enable_progress_streaming=enable_progress_streaming,
            progress_update_interval_seconds=progress_update_interval_seconds,
            enable_verifier=enable_verifier,
            reminders_egress=reminders_egress,
            reminders_archive_list_name=reminders_archive_list_name,
            notes_egress=notes_egress,
            notes_archive_folder_name=notes_archive_folder_name,
            calendar_egress=calendar_egress,
            scheduler=scheduler,
            log_notes_egress=log_notes_egress,
            notes_log_folder_name=notes_log_folder_name,
        )

    # --- Workspace Resolution ---

    def _resolve_workspace(self, alias: str) -> str:
        if not alias:
            return self.default_workspace
        resolved = self.workspace_aliases.get(alias)
        if resolved and self._is_workspace_allowed(resolved):
            return resolved
        return self.default_workspace

    # --- Main Handler ---

    def handle_message(self, message: InboundMessage) -> OrchestrationResult:
        dedupe_hash = f"{message.sender}:{message.id}"
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
                    "Or use `idea:`, `plan:`, `task:`, `project:`, `health`, `history:`, or `usage`."
                )
                self.egress.send(message.sender, hint)
                return OrchestrationResult(kind=CommandKind.CHAT, response=hint)
        elif command.kind is CommandKind.CHAT and not self.require_chat_prefix:
            if raw_text.lower().startswith(self.chat_prefix.lower()):
                stripped = raw_text[len(self.chat_prefix) :].strip()
                command = ParsedCommand(kind=CommandKind.CHAT, payload=stripped, workspace=command.workspace)

        if command.kind is CommandKind.HEALTH:
            return self._handle_health(message.sender)

        if command.kind is CommandKind.HISTORY:
            return self._handle_history(message.sender, command.payload)

        if command.kind is CommandKind.USAGE:
            return self._handle_usage(message.sender, command.payload)

        if command.kind is CommandKind.LOGS:
            return self._handle_logs(message.sender, command.payload)

        if command.kind is CommandKind.STATUS:
            pending = self.store.list_pending_approvals()
            if not pending:
                response = "No pending approvals."
            else:
                lines = [f"Pending approvals ({len(pending)}):"]
                for req in pending:
                    req_id = req.get("request_id", "?")
                    summary = req.get("summary", "")
                    preview = req.get("command_preview", "")[:80].replace("\n", " ")
                    lines.append(f"\n{req_id}")
                    lines.append(f"  {preview}")
                lines.append(f"\nReply `approve <id>` or `deny <id>` to act on one.")
                lines.append("Reply `deny all` to cancel all.")
                response = "\n".join(lines)
            self.egress.send(message.sender, response)
            return OrchestrationResult(kind=command.kind, response=response)

        if command.kind is CommandKind.DENY_ALL:
            if not hasattr(self.store, "deny_all_approvals"):
                response = "deny all not supported by this store."
            else:
                count = self.store.deny_all_approvals()
                response = f"Cancelled {count} pending approval{'s' if count != 1 else ''}." if count else "No pending approvals to cancel."
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
            return self._approval.resolve(message.sender, command.kind, command.payload)

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
            return self._approval.handle_approval_required(
                message, command.kind, thread_id, command.payload, workspace,
                default_workspace=self.default_workspace,
                is_workspace_allowed=self._is_workspace_allowed,
            )

        prompt = self._build_non_mutating_prompt(command.kind, command.payload, workspace)
        prompt = self._inject_auto_context(message.sender, prompt)
        prompt = self._inject_attachment_context(message, prompt)
        prompt = self._inject_memory_context(prompt)

        response = self.connector.run_turn(thread_id, prompt)
        self.egress.send(message.sender, response)
        self._log_to_notes(command.kind.value, message.sender, command.payload, response)
        return OrchestrationResult(kind=command.kind, response=response)

    # --- Health Dashboard ---

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

    # --- Logs ---

    def _handle_logs(self, sender: str, payload: str) -> OrchestrationResult:
        n = 20
        if payload.strip():
            try:
                requested = int(payload.strip())
                n = max(1, min(requested, 50))
            except ValueError:
                pass

        log_path: Path | None = None
        if self.log_file_path:
            candidate = Path(self.log_file_path)
            if not candidate.is_absolute():
                # Resolve relative to repo root (two levels above this file)
                candidate = Path(__file__).resolve().parents[2] / self.log_file_path
            if candidate.exists():
                log_path = candidate

        if log_path is None:
            response = f"Log file not found: {self.log_file_path or '(not configured)'}"
        else:
            try:
                raw_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                tail = raw_lines[-n:] if len(raw_lines) >= n else raw_lines
                clean = [_ANSI_ESCAPE.sub("", line) for line in tail]
                response = f"Last {len(clean)} lines of {log_path.name}:\n" + "\n".join(clean)
            except OSError as exc:
                response = f"Could not read log file: {exc}"

        self.egress.send(sender, response)
        return OrchestrationResult(kind=CommandKind.LOGS, response=response)

    # --- Token Usage (ccusage) ---

    def _handle_usage(self, sender: str, payload: str) -> OrchestrationResult:
        sub = payload.lower().strip()

        if sub in ("monthly", "month"):
            cmd = ["npx", "--yes", "ccusage", "monthly", "--json"]
            mode = "monthly"
        elif sub in ("blocks", "block"):
            cmd = ["npx", "--yes", "ccusage", "blocks", "--json"]
            mode = "blocks"
        elif sub == "today":
            since = datetime.now(UTC).strftime("%Y%m%d")
            cmd = ["npx", "--yes", "ccusage", "daily", "--json", "--since", since]
            mode = "daily"
        else:
            since = (datetime.now(UTC) - timedelta(days=6)).strftime("%Y%m%d")
            cmd = ["npx", "--yes", "ccusage", "daily", "--json", "--since", since]
            mode = "daily"

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            response = "Usage data unavailable: ccusage timed out."
            self.egress.send(sender, response)
            return OrchestrationResult(kind=CommandKind.USAGE, response=response)
        except (json.JSONDecodeError, FileNotFoundError, Exception) as exc:
            response = f"Usage data unavailable: {exc}"
            self.egress.send(sender, response)
            return OrchestrationResult(kind=CommandKind.USAGE, response=response)

        lines: list[str] = []

        if mode == "daily":
            rows = data.get("daily", [])
            if not rows:
                lines.append("No usage data found.")
            else:
                lines.append("Token usage (last 7 days):")
                total_cost = 0.0
                for row in rows:
                    tokens = row["totalTokens"]
                    cost = row["totalCost"]
                    total_cost += cost
                    tok_str = f"{tokens / 1_000_000:.2f}M" if tokens >= 1_000_000 else f"{tokens / 1_000:.0f}K"
                    lines.append(f"  {row['date']}: {tok_str} tokens  ${cost:.2f}")
                lines.append(f"Total: ${total_cost:.2f}")

        elif mode == "monthly":
            rows = data.get("monthly", [])
            if not rows:
                lines.append("No usage data found.")
            else:
                lines.append("Monthly token usage:")
                for row in rows:
                    month = row.get("month", row.get("date", "?"))
                    tokens = row["totalTokens"]
                    cost = row["totalCost"]
                    tok_str = f"{tokens / 1_000_000:.2f}M" if tokens >= 1_000_000 else f"{tokens / 1_000:.0f}K"
                    lines.append(f"  {month}: {tok_str}  ${cost:.2f}")

        elif mode == "blocks":
            active_blocks = [b for b in data.get("blocks", []) if not b.get("isGap")]
            if not active_blocks:
                lines.append("No billing blocks found.")
            else:
                lines.append("Recent billing blocks (5-hr windows):")
                for block in active_blocks[-5:]:
                    start = block["startTime"][:16].replace("T", " ")
                    cost = block.get("costUSD", 0)
                    tokens = block.get("totalTokens", 0)
                    active_tag = " [ACTIVE]" if block.get("isActive") else ""
                    tok_str = f"{tokens / 1_000_000:.2f}M" if tokens >= 1_000_000 else f"{tokens / 1_000:.0f}K"
                    lines.append(f"  {start}: {tok_str}  ${cost:.2f}{active_tag}")

        response = "\n".join(lines)
        self.egress.send(sender, response)
        return OrchestrationResult(kind=CommandKind.USAGE, response=response)

    # --- Conversation Memory ---

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
        elif sub == "mute":
            self.store.set_state("companion_muted", "true")
            response = "Companion muted. Send 'system: unmute' to re-enable proactive messages."
            self.egress.send(sender, response)
        elif sub == "unmute":
            self.store.set_state("companion_muted", "false")
            response = "Companion unmuted. Proactive messages re-enabled."
            self.egress.send(sender, response)
        elif sub in ("sync office", "sync"):
            if self.office_syncer:
                try:
                    result = self.office_syncer.sync_all()
                    response = "Synced: " + ", ".join(f"{t}={n}" for t, n in result.items())
                except Exception as exc:
                    response = f"Office sync failed: {exc}"
            else:
                response = "Office sync not enabled. Set apple_flow_enable_office_sync=true and apple_flow_supabase_service_key."
            self.egress.send(sender, response)
        else:
            response = "Unknown system command. Use: system: stop | restart | mute | unmute | sync office"
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

    # --- Memory Context Injection ---

    def _inject_memory_context(self, prompt: str) -> str:
        if not self.memory:
            return prompt
        try:
            context = self.memory.get_context_for_prompt()
            if context:
                return f"Persistent memory context:\n{context}\n\n{prompt}"
        except Exception:
            pass
        return prompt

    # --- Attachment Context ---

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

    # --- Notes Logging (delegated) ---

    def _log_to_notes(self, kind: str, sender: str, request: str, response: str) -> None:
        log_to_notes(self.log_notes_egress, self.notes_log_folder_name, kind, sender, request, response)

    # --- Prompt Building ---

    def _build_unified_prompt(self, payload: str, workspace: str | None = None) -> str:
        return payload

    def _build_non_mutating_prompt(self, kind: CommandKind, payload: str, workspace: str | None = None) -> str:
        if kind is CommandKind.IDEA:
            return f"brainstorm mode: generate options, trade-offs, and recommendation. request={payload}"
        if kind is CommandKind.PLAN:
            return f"planning mode: create a stepwise implementation plan with acceptance criteria. goal={payload}"
        return self._build_unified_prompt(payload, workspace)

    def _is_workspace_allowed(self, candidate: str) -> bool:
        target = Path(candidate).resolve()
        for allowed_path in self._allowed_workspace_set:
            if allowed_path == target or allowed_path in target.parents:
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
