from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from .agent_teams import AgentTeamCatalog
from .approval import ApprovalHandler, OrchestrationResult
from .commanding import CommandKind, ParsedCommand, is_likely_mutating, parse_command
from .healer_scan import FlowHealerScanner
from .healer_tracker import GitHubHealerTracker
from .models import InboundMessage, RunState
from .notes_logging import log_to_notes
from .protocols import ConnectorProtocol, EgressProtocol, StoreProtocol
from .utils import normalize_sender

logger = logging.getLogger("apple_flow.orchestrator")

if TYPE_CHECKING:
    from .attachments import AttachmentProcessor
    from .memory import FileMemory
    from .memory_v2 import MemoryService
    from .office_sync import OfficeSyncer
    from .run_executor import RunExecutor
    from .scheduler import FollowUpScheduler

_SEP = "━" * 30
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_FILE_ALIAS_RE = re.compile(r"@f:([A-Za-z0-9][\w.-]*)")


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
        file_aliases: dict[str, str] | None = None,
        auto_context_messages: int = 0,
        enable_progress_streaming: bool = False,
        progress_update_interval_seconds: float = 30.0,
        execution_heartbeat_seconds: float = 120.0,
        checkpoint_on_timeout: bool = True,
        auto_resume_on_timeout: bool = False,
        max_resume_attempts: int = 5,
        enable_verifier: bool = False,
        enable_attachments: bool = False,
        attachment_processor: AttachmentProcessor | None = None,
        personality_prompt: str = "",
        reminders_egress: Any = None,
        reminders_archive_list_name: str = "agent-archive",
        notes_egress: Any = None,
        notes_archive_folder_name: str = "agent-archive",
        calendar_egress: Any = None,
        shutdown_callback: Callable[[], None] | None = None,
        log_notes_egress: Any = None,
        notes_log_folder_name: str = "agent-logs",
        memory: FileMemory | None = None,
        memory_service: MemoryService | None = None,
        scheduler: FollowUpScheduler | None = None,
        run_executor: RunExecutor | None = None,
        office_syncer: OfficeSyncer | None = None,
        log_file_path: str | None = None,
        approval_sender_override: str = "",
        healer_repo_path: str = "",
        healer_scan_enable_issue_creation: bool = True,
        healer_scan_max_issues_per_run: int = 5,
        healer_scan_severity_threshold: str = "medium",
        healer_scan_default_labels: list[str] | None = None,
        healer_scan_notes_log: bool = False,
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
        self.file_aliases = file_aliases or {}
        self.auto_context_messages = auto_context_messages
        self.enable_progress_streaming = enable_progress_streaming
        self.enable_attachments = enable_attachments
        self.attachment_processor = attachment_processor
        self.personality_prompt = personality_prompt
        self.shutdown_callback = shutdown_callback
        self.log_notes_egress = log_notes_egress
        self.notes_log_folder_name = notes_log_folder_name
        self.memory = memory
        self.memory_service = memory_service
        self.office_syncer = office_syncer
        self.log_file_path = log_file_path
        self.team_catalog = AgentTeamCatalog(Path(__file__).resolve().parents[2])
        self.healer_repo_path = (healer_repo_path or "").strip()
        self.healer_scan_enable_issue_creation = bool(healer_scan_enable_issue_creation)
        self.healer_scan_max_issues_per_run = max(1, int(healer_scan_max_issues_per_run))
        self.healer_scan_severity_threshold = (healer_scan_severity_threshold or "medium").strip().lower()
        self.healer_scan_default_labels = healer_scan_default_labels or ["healer:ready", "kind:scan"]
        self.healer_scan_notes_log = bool(healer_scan_notes_log)

        self._approval = ApprovalHandler(
            connector=connector,
            egress=egress,
            store=store,
            approval_ttl_minutes=approval_ttl_minutes,
            enable_progress_streaming=enable_progress_streaming,
            progress_update_interval_seconds=progress_update_interval_seconds,
            execution_heartbeat_seconds=execution_heartbeat_seconds,
            checkpoint_on_timeout=checkpoint_on_timeout,
            auto_resume_on_timeout=auto_resume_on_timeout,
            max_resume_attempts=max_resume_attempts,
            enable_verifier=enable_verifier,
            reminders_egress=reminders_egress,
            reminders_archive_list_name=reminders_archive_list_name,
            notes_egress=notes_egress,
            notes_archive_folder_name=notes_archive_folder_name,
            calendar_egress=calendar_egress,
            scheduler=scheduler,
            run_executor=run_executor,
            log_notes_egress=log_notes_egress,
            notes_log_folder_name=notes_log_folder_name,
            approval_sender_override=approval_sender_override,
        )

    def set_run_executor(self, run_executor: Any) -> None:
        """Attach a background run executor after orchestrator construction."""
        self._approval.run_executor = run_executor

    def _send(self, recipient: str, text: str, context: dict[str, Any] | None = None) -> None:
        try:
            self.egress.send(recipient, text, context=context)
        except TypeError:
            self.egress.send(recipient, text)

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

        self._prepare_attachment_context(message)
        raw_text = message.text.strip()
        if not raw_text:
            if self.enable_attachments and (
                message.context.get("attachments") or message.context.get("attachment_prompt_block")
            ):
                synthetic = "analyze attached files"
                if self.require_chat_prefix:
                    chat_prefix = self.chat_prefix or "relay:"
                    synthetic = f"{chat_prefix} {synthetic}"
                message.text = synthetic
                raw_text = synthetic
                logger.info("Synthesized attachment-only prompt for sender=%s message_id=%s", message.sender, message.id)
            else:
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
                    "Or use `help`, `idea:`, `plan:`, `task:`, `project:`, `health`, `history:`, or `usage`."
                )
                self._send(message.sender, hint, context=message.context)
                return OrchestrationResult(kind=CommandKind.CHAT, response=hint)
        elif command.kind is CommandKind.CHAT and not self.require_chat_prefix:
            if raw_text.lower().startswith(self.chat_prefix.lower()):
                stripped = raw_text[len(self.chat_prefix) :].strip()
                command = ParsedCommand(kind=CommandKind.CHAT, payload=stripped, workspace=command.workspace)

        if command.kind is CommandKind.HEALTH:
            return self._handle_health(message.sender, context=message.context)

        if command.kind is CommandKind.HELP:
            return self._handle_help(message.sender, command.payload, context=message.context)

        if command.kind is CommandKind.HISTORY:
            return self._handle_history(message.sender, command.payload, context=message.context)

        if command.kind is CommandKind.USAGE:
            return self._handle_usage(message.sender, command.payload, context=message.context)

        if command.kind is CommandKind.LOGS:
            return self._handle_logs(message.sender, command.payload, context=message.context)

        if command.kind is CommandKind.STATUS:
            return self._handle_status(message.sender, command.payload, context=message.context)

        if command.kind is CommandKind.DENY_ALL:
            if not hasattr(self.store, "deny_all_approvals"):
                response = "deny all not supported by this store."
            else:
                count = self.store.deny_all_approvals()
                response = f"Cancelled {count} pending approval{'s' if count != 1 else ''}." if count else "No pending approvals to cancel."
            self._send(message.sender, response, context=message.context)
            return OrchestrationResult(kind=command.kind, response=response)

        if command.kind is CommandKind.CLEAR_CONTEXT:
            if hasattr(self.connector, "reset_thread"):
                thread_id = self.connector.reset_thread(message.sender)
            else:
                thread_id = self.connector.get_or_create_thread(message.sender)
            self.store.upsert_session(message.sender, thread_id, CommandKind.CHAT.value)
            response = "Started a fresh chat context for this sender."
            self._send(message.sender, response, context=message.context)
            return OrchestrationResult(kind=command.kind, response=response)

        if command.kind in {CommandKind.APPROVE, CommandKind.DENY}:
            return self._approval.resolve(message.sender, command.kind, command.payload)

        if command.kind is CommandKind.SYSTEM:
            return self._handle_system(message, command.payload)

        payload, file_alias_mappings, file_alias_warnings = self._resolve_file_aliases(command.payload)
        if payload != command.payload:
            command = ParsedCommand(kind=command.kind, payload=payload, workspace=command.workspace)
        if file_alias_warnings:
            self._send(
                message.sender,
                "File alias warnings:\n" + "\n".join(f"- {line}" for line in file_alias_warnings),
                context=message.context,
            )

        # Natural language mode: auto-promote bare CHAT messages with mutating intent to TASK
        if (
            command.kind is CommandKind.CHAT
            and not self.require_chat_prefix
            and message.context.get("channel") != "mail"
            and is_likely_mutating(command.payload)
        ):
            command = ParsedCommand(kind=CommandKind.TASK, payload=command.payload, workspace=command.workspace)

        active_team = self._get_active_team(message.sender)
        team_context = None
        if command.kind in {CommandKind.IDEA, CommandKind.PLAN, CommandKind.TASK, CommandKind.PROJECT}:
            team_context = self._build_turn_team_context(active_team)

        workspace = self._resolve_workspace(command.workspace)

        thread_id = self.connector.get_or_create_thread(message.sender)
        self.store.upsert_session(message.sender, thread_id, command.kind.value)

        if command.kind in {CommandKind.TASK, CommandKind.PROJECT}:
            result = self._approval.handle_approval_required(
                message, command.kind, thread_id, command.payload, workspace,
                default_workspace=self.default_workspace,
                is_workspace_allowed=self._is_workspace_allowed,
                team_context=team_context,
            )
            if result.run_id and team_context:
                self._consume_active_team(message.sender)
            return result

        if command.kind in {CommandKind.IDEA, CommandKind.PLAN} and team_context:
            self._consume_active_team(message.sender)

        prompt = self._build_non_mutating_prompt(command.kind, command.payload, workspace)
        if file_alias_mappings:
            prompt = "Referenced file aliases:\n" + "\n".join(
                f"- @f:{alias} -> {resolved}" for alias, resolved in file_alias_mappings
            ) + f"\n\n{prompt}"
        if file_alias_warnings:
            prompt = "File alias warnings:\n" + "\n".join(
                f"- {line}" for line in file_alias_warnings
            ) + f"\n\n{prompt}"
        prompt = self._apply_team_prompt_fallback(prompt, team_context)
        prompt = self._inject_auto_context(message.sender, prompt)
        prompt = self._inject_attachment_context(message, prompt)
        prompt = self._inject_memory_context(prompt)

        response = self._run_non_mutating_turn(
            sender=message.sender,
            thread_id=thread_id,
            prompt=prompt,
            context=message.context,
            team_context=team_context,
            allow_tools=True,
        )
        self._send(message.sender, response, context=message.context)
        self._log_to_notes(command.kind.value, message.sender, command.payload, response)
        return OrchestrationResult(kind=command.kind, response=response)

    # --- Health Dashboard ---

    def _handle_help(self, sender: str, payload: str, context: dict[str, Any] | None = None) -> OrchestrationResult:
        topic = payload.strip().lower()
        if topic:
            response = (
                "Help topics are not yet segmented.\n"
                "Send `help` to see all commands and tips."
            )
            self._send(sender, response, context=context)
            return OrchestrationResult(kind=CommandKind.HELP, response=response)

        lines = [
            "🤖 Apple Flow help",
            "",
            "📚 Core commands:",
            "- ❓ help — show this guide",
            "- 📊 status — list pending approvals + active runs",
            "- 🔎 status <run_id|request_id> — inspect one run/request",
            "- ✅ approve <id> / ❌ deny <id> / 🗑️ deny all — approval controls",
            "- 🔄 clear context — reset this sender's chat context",
            "",
            "💬 Conversation modes:",
            "- 💬 relay: <message> — general chat (when prefix mode is enabled)",
            "- 💡 idea: <request> — brainstorming and options",
            "- 📋 plan: <request> — implementation planning",
            "- ⚡ task: <request> — execute a concrete task (approval required)",
            "- 🚀 project: <request> — multi-step work (approval required)",
            "",
            "🏥 Diagnostics:",
            "- 🏥 health — daemon + companion status",
            "- 🔍 history: [query] — recent conversation history",
            "- 📈 usage — token usage stats",
            "- 📋 logs — tail the daemon log",
            "",
            "🔧 System controls:",
            "- 🔧 system: stop | restart | kill provider | cancel run <run_id>",
            "- 🔇 system: mute | unmute",
            "- 🩺 system: healer | healer pause | healer resume | healer scan [dry-run]",
            "- 🔄 system: sync office",
            "- 🧩 system: teams list | team load <slug> | team current | team unload",
            "",
            "🧠 Tips:",
            "- Use `status` first when something seems stuck.",
            "- Use `approve <id> <extra instructions>` to resume with guidance.",
            "- Use `@alias` right after `idea:/plan:/task:/project:` to target a workspace.",
        ]
        response = "\n".join(lines)
        self._send(sender, response, context=context)
        return OrchestrationResult(kind=CommandKind.HELP, response=response)

    def _handle_status(self, sender: str, payload: str, context: dict[str, Any] | None = None) -> OrchestrationResult:
        if payload:
            response = self._status_for_target(payload)
        else:
            response = self._status_overview()
        self._send(sender, response, context=context)
        return OrchestrationResult(kind=CommandKind.STATUS, response=response)

    def _status_overview(self) -> str:
        pending = self.store.list_pending_approvals()
        lines: list[str] = []

        if not pending:
            lines.append("No pending approvals.")
        else:
            lines.append(f"Pending approvals ({len(pending)}):")
            for req in pending:
                req_id = req.get("request_id", "?")
                preview = (req.get("command_preview", "") or "")[:80].replace("\n", " ")
                lines.append(f"\n{req_id}")
                lines.append(f"  {preview}")
            lines.append("\nReply `approve <id>` or `deny <id>` to act on one.")
            lines.append("Reply `deny all` to cancel all.")

        active_runs: list[dict[str, Any]] = []
        if hasattr(self.store, "list_active_runs"):
            active_runs = self.store.list_active_runs(limit=10)
        elif hasattr(self.store, "get_stats"):
            runs_by_state = self.store.get_stats().get("runs_by_state", {})
            active_count = sum(
                runs_by_state.get(state, 0)
                for state in ["planning", "queued", "running", "executing", "verifying", "awaiting_approval"]
            )
            if active_count:
                lines.append(f"\nActive runs: {active_count} (details unavailable in this store)")

        if active_runs:
            lines.append(f"\nActive runs ({len(active_runs)}):")
            for run in active_runs:
                run_id = run.get("run_id", "?")
                state = run.get("state", "?")
                intent = run.get("intent", "?")
                updated = run.get("updated_at", "?")
                snippet = ""
                if hasattr(self.store, "get_latest_event_for_run"):
                    latest_event = self.store.get_latest_event_for_run(run_id)
                    if latest_event:
                        event_type = latest_event.get("event_type", "")
                        payload = latest_event.get("payload", {})
                        if isinstance(payload, dict):
                            raw_snippet = payload.get("snippet") or payload.get("reason", "")
                            if raw_snippet:
                                snippet = f" | {event_type}: {str(raw_snippet)[:60]}"
                lines.append(f"  {run_id} [{intent}] {state} (updated: {updated}){snippet}")

            lines.append("\nUse `status <run_id>` or `status <request_id>` for details.")

        return "\n".join(lines)

    def _status_for_target(self, target: str) -> str:
        target = target.strip()
        if not target:
            return self._status_overview()

        approval = self.store.get_approval(target)
        run_id = None
        if approval:
            run_id = approval.get("run_id")
        elif target.startswith("run_"):
            run_id = target
        else:
            maybe_run = self.store.get_run(target)
            if maybe_run:
                run_id = target

        if not run_id:
            return f"No run or approval found for `{target}`."

        run = self.store.get_run(run_id)
        if not run:
            return f"Run `{run_id}` not found."

        lines = [
            f"Run: {run_id}",
            f"State: {run.get('state', '?')}",
            f"Intent: {run.get('intent', '?')}",
            f"Workspace: {run.get('cwd', '?')}",
            f"Created: {run.get('created_at', '?')}",
            f"Updated: {run.get('updated_at', '?')}",
        ]

        if approval:
            lines.append(
                f"Approval: {approval.get('request_id', '?')} ({approval.get('status', '?')}, "
                f"expires {approval.get('expires_at', '?')})"
            )

        events: list[dict[str, Any]] = []
        if hasattr(self.store, "list_events_for_run"):
            events = self.store.list_events_for_run(run_id, limit=8)
        elif hasattr(self.store, "list_events"):
            all_events = self.store.list_events(limit=200)
            events = [event for event in all_events if event.get("run_id") == run_id][:8]

        if events:
            lines.append("Recent events:")
            for event in events:
                payload = event.get("payload", {})
                snippet = ""
                if isinstance(payload, dict):
                    snippet = payload.get("snippet") or payload.get("reason") or payload.get("request_id") or ""
                lines.append(
                    f"  - {event.get('created_at', '?')} {event.get('step', '?')}:"
                    f"{event.get('event_type', '?')} {str(snippet)[:80]}"
                )
        else:
            lines.append("Recent events: none")

        return "\n".join(lines)

    def _handle_health(self, sender: str, context: dict[str, Any] | None = None) -> OrchestrationResult:
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

        companion_last_check = self.store.get_state("companion_last_check_at")
        if companion_last_check:
            try:
                check_dt = datetime.fromisoformat(companion_last_check)
                minutes_ago = int((datetime.now() - check_dt).total_seconds() / 60)
                obs_count = self.store.get_state("companion_last_obs_count") or "?"
                skip_reason = self.store.get_state("companion_last_skip_reason") or ""
                sent_at = self.store.get_state("companion_last_sent_at")
                hour_count = self.store.get_state("companion_proactive_hour_count") or "0"
                muted = self.store.get_state("companion_muted") == "true"

                status = f"Companion: last check {minutes_ago}m ago | {obs_count} obs found"
                if skip_reason:
                    status += f" | skipped ({skip_reason})"
                if sent_at:
                    sent_dt = datetime.fromisoformat(sent_at)
                    sent_min = int((datetime.now() - sent_dt).total_seconds() / 60)
                    status += f" | last sent {sent_min}m ago"
                status += f" | {hour_count}/hr sent"
                if muted:
                    status += " | MUTED"
                parts.append(status)
            except (ValueError, TypeError):
                parts.append("Companion: enabled (no check recorded yet)")

        response = "\n".join(parts)
        self._send(sender, response, context=context)
        return OrchestrationResult(kind=CommandKind.HEALTH, response=response)

    # --- Logs ---

    def _handle_logs(self, sender: str, payload: str, context: dict[str, Any] | None = None) -> OrchestrationResult:
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

        self._send(sender, response, context=context)
        return OrchestrationResult(kind=CommandKind.LOGS, response=response)

    # --- Token Usage (ccusage) ---

    def _handle_usage(self, sender: str, payload: str, context: dict[str, Any] | None = None) -> OrchestrationResult:
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
            self._send(sender, response, context=context)
            return OrchestrationResult(kind=CommandKind.USAGE, response=response)
        except (json.JSONDecodeError, FileNotFoundError, Exception) as exc:
            response = f"Usage data unavailable: {exc}"
            self._send(sender, response, context=context)
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
        self._send(sender, response, context=context)
        return OrchestrationResult(kind=CommandKind.USAGE, response=response)

    # --- Conversation Memory ---

    def _handle_history(self, sender: str, query: str, context: dict[str, Any] | None = None) -> OrchestrationResult:
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

        self._send(sender, response, context=context)
        return OrchestrationResult(kind=CommandKind.HISTORY, response=response)

    # --- System Command ---

    def _restart_launchd_service(self, label: str = "local.apple-flow") -> bool:
        """Restart a launchd service in-place via kickstart.

        Returns True if launchd accepted the restart request.
        """
        target = f"gui/{os.getuid()}/{label}"
        try:
            result = subprocess.run(
                ["launchctl", "kickstart", "-k", target],
                check=False,
                timeout=8,
            )
            if result.returncode == 0:
                return True
            logger.warning(
                "launchctl kickstart failed for %s (exit=%s)",
                target,
                result.returncode,
            )
        except Exception as exc:
            logger.warning("Failed to trigger launchctl kickstart for %s: %s", target, exc)
        return False

    def _provider_label(self) -> str:
        name = self.connector.__class__.__name__.lower()
        if "gemini" in name:
            return "Gemini"
        if "claude" in name:
            return "Claude"
        if "ollama" in name:
            return "Ollama"
        if "cline" in name:
            return "Cline"
        if "codex" in name:
            return "Codex"
        return self.connector.__class__.__name__

    def _provider_command_patterns(self) -> list[str]:
        patterns: list[str] = []
        for attr in ("gemini_command", "claude_command", "codex_command", "cline_command", "ollama_command"):
            raw = getattr(self.connector, attr, "")
            if not isinstance(raw, str):
                continue
            value = raw.strip().lower()
            if not value:
                continue
            patterns.append(value)
            patterns.append(Path(value).name)
        provider = self._provider_label().lower()
        if provider:
            patterns.append(provider)
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for pattern in patterns:
            if pattern and pattern not in seen:
                seen.add(pattern)
                deduped.append(pattern)
        return deduped

    @staticmethod
    def _load_process_table() -> dict[int, tuple[int, str]]:
        """Return process table as {pid: (ppid, command)}."""
        table: dict[int, tuple[int, str]] = {}
        try:
            result = subprocess.run(
                ["ps", "-axo", "pid=,ppid=,command="],
                capture_output=True,
                text=True,
                check=False,
                timeout=8,
            )
        except Exception:
            return table
        if result.returncode != 0:
            return table
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[0])
                ppid = int(parts[1])
            except ValueError:
                continue
            table[pid] = (ppid, parts[2])
        return table

    @staticmethod
    def _collect_descendants(table: dict[int, tuple[int, str]], root_pid: int) -> set[int]:
        descendants: set[int] = set()
        frontier = [root_pid]
        while frontier:
            parent = frontier.pop()
            for pid, (ppid, _) in table.items():
                if ppid == parent and pid not in descendants:
                    descendants.add(pid)
                    frontier.append(pid)
        return descendants

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _mark_inflight_runs_cancelled(self, reason: str) -> int:
        if not hasattr(self.store, "list_active_runs") or not hasattr(self.store, "update_run_state"):
            return 0
        runs = self.store.list_active_runs(limit=200)
        if not runs:
            return 0
        inflight_states = {
            RunState.PLANNING.value,
            RunState.QUEUED.value,
            RunState.RUNNING.value,
            RunState.EXECUTING.value,
            RunState.VERIFYING.value,
        }
        updated = 0
        for run in runs:
            run_id = run.get("run_id")
            state = str(run.get("state", ""))
            if not run_id or state not in inflight_states:
                continue
            if hasattr(self.store, "cancel_run_jobs"):
                self.store.cancel_run_jobs(run_id)
            self.store.update_run_state(run_id, RunState.CANCELLED.value)
            self._create_event(
                run_id=run_id,
                step="executor",
                event_type="execution_cancelled",
                payload={"reason": reason, "source": "system_killswitch"},
            )
            updated += 1
        return updated

    def _kill_provider_processes(self) -> str:
        provider = self._provider_label()
        killed_tracked = 0
        if hasattr(self.connector, "cancel_active_processes"):
            try:
                killed_tracked = int(self.connector.cancel_active_processes())
            except Exception:
                logger.exception("Connector cancel_active_processes failed")

        patterns = self._provider_command_patterns()
        table = self._load_process_table()
        if not patterns or not table:
            reconciled = self._mark_inflight_runs_cancelled("killswitch requested (process inspection unavailable)")
            if killed_tracked:
                base = f"Killed {killed_tracked} tracked {provider} process(es)."
                if reconciled:
                    return f"{base} Cancelled {reconciled} in-flight run(s)."
                return base
            if reconciled:
                return (
                    f"Could not inspect running {provider} processes. "
                    f"Cancelled {reconciled} in-flight run(s)."
                )
            return f"Could not inspect running {provider} processes."

        daemon_pid = os.getpid()
        descendants = self._collect_descendants(table, daemon_pid)
        if not descendants:
            reconciled = self._mark_inflight_runs_cancelled("killswitch requested (no subprocess descendants)")
            if killed_tracked or reconciled:
                return (
                    f"Killed {killed_tracked} tracked {provider} process(es). "
                    f"Cancelled {reconciled} in-flight run(s)."
                )
            return f"No active {provider} provider subprocesses found."

        matching_roots = {
            pid
            for pid in descendants
            if any(pattern in table[pid][1].lower() for pattern in patterns)
        }
        if not matching_roots:
            reconciled = self._mark_inflight_runs_cancelled("killswitch requested (no matching subprocesses)")
            if killed_tracked or reconciled:
                return (
                    f"Killed {killed_tracked} tracked {provider} process(es). "
                    f"Cancelled {reconciled} in-flight run(s)."
                )
            return f"No active {provider} provider subprocesses found."

        # Kill matching provider processes and any descendants they spawned.
        to_kill = set(matching_roots)
        frontier = list(matching_roots)
        while frontier:
            parent = frontier.pop()
            for pid, (ppid, _) in table.items():
                if ppid == parent and pid not in to_kill:
                    to_kill.add(pid)
                    frontier.append(pid)

        terminated = 0
        for pid in sorted(to_kill, reverse=True):
            try:
                os.kill(pid, signal.SIGTERM)
                terminated += 1
            except ProcessLookupError:
                continue
            except PermissionError:
                logger.warning("Permission denied sending SIGTERM to pid=%s", pid)

        time.sleep(0.2)

        force_killed = 0
        for pid in sorted(to_kill, reverse=True):
            if not self._pid_alive(pid):
                continue
            try:
                os.kill(pid, signal.SIGKILL)
                force_killed += 1
            except ProcessLookupError:
                continue
            except PermissionError:
                logger.warning("Permission denied sending SIGKILL to pid=%s", pid)

        reconciled = self._mark_inflight_runs_cancelled("provider process killed by system command")
        total_killed = killed_tracked + terminated + force_killed
        if total_killed == 0:
            if reconciled:
                return f"No active {provider} provider subprocesses found. Cancelled {reconciled} in-flight run(s)."
            return f"No active {provider} provider subprocesses found."
        if force_killed:
            base = (
                f"Killed {total_killed} active {provider} provider process(es) "
                f"({force_killed} required SIGKILL)."
            )
            if reconciled:
                return f"{base} Cancelled {reconciled} in-flight run(s)."
            return base
        base = f"Killed {total_killed} active {provider} provider process(es)."
        if reconciled:
            return f"{base} Cancelled {reconciled} in-flight run(s)."
        return base

    def _cancel_run_by_id(self, run_id: str) -> str:
        run_id = run_id.strip()
        if not run_id:
            return "Usage: `system: cancel run <run_id>`"
        run = self.store.get_run(run_id) if hasattr(self.store, "get_run") else None
        if not run:
            return f"Run `{run_id}` not found."

        state = str(run.get("state", ""))
        terminal_states = {
            RunState.COMPLETED.value,
            RunState.FAILED.value,
            RunState.DENIED.value,
            RunState.CANCELLED.value,
        }
        if state in terminal_states:
            return f"Run `{run_id}` is already `{state}`."

        sender = str(run.get("sender", "")).strip()
        killed = 0
        if hasattr(self.connector, "cancel_active_processes"):
            try:
                killed = int(self.connector.cancel_active_processes(sender or None))
            except Exception:
                logger.exception("Connector cancel_active_processes failed for run_id=%s", run_id)

        cancelled_jobs = 0
        if hasattr(self.store, "cancel_run_jobs"):
            cancelled_jobs = int(self.store.cancel_run_jobs(run_id))

        if hasattr(self.store, "update_run_state"):
            self.store.update_run_state(run_id, RunState.CANCELLED.value)
        self._create_event(
            run_id=run_id,
            step="executor",
            event_type="execution_cancelled",
            payload={
                "reason": "cancel run requested by system command",
                "source": "system_cancel_run",
                "killed_processes": killed,
                "cancelled_jobs": cancelled_jobs,
            },
        )
        return (
            f"Cancelled run `{run_id}`. "
            f"Killed {killed} process(es), cancelled {cancelled_jobs} queued/running job(s)."
        )

    def _handle_system(self, message: InboundMessage, subcommand: str) -> OrchestrationResult:
        sender = message.sender
        action, slug, remainder = self._parse_team_system_command(subcommand)
        if action:
            return self._handle_team_system(message, action, slug, remainder)

        sub = subcommand.strip().lower()
        if sub == "stop":
            response = "Apple Flow shutting down..."
            self._send(sender, response, context=message.context)
            if self.shutdown_callback is not None:
                self.shutdown_callback()
        elif sub == "restart":
            response = "Apple Flow restarting... (text 'health' to confirm it's back)"
            self._mark_restart_echo_suppress(sender, response)
            self._send(sender, response, context=message.context)
            restarted = self._restart_launchd_service()
            if not restarted and self.shutdown_callback is not None:
                # Fallback for non-launchd runs: perform a graceful shutdown and let
                # the external caller/supervisor bring the process back up.
                self.shutdown_callback()
        elif sub in {"kill provider", "killswitch", "kill ai"}:
            response = self._kill_provider_processes()
            self._send(sender, response, context=message.context)
        elif sub.startswith("cancel run "):
            response = self._cancel_run_by_id(sub.split(" ", 2)[2])
            self._send(sender, response, context=message.context)
        elif sub.startswith("cancel "):
            response = self._cancel_run_by_id(sub.split(" ", 1)[1])
            self._send(sender, response, context=message.context)
        elif sub == "mute":
            self.store.set_state("companion_muted", "true")
            response = "Companion muted. Send 'system: unmute' to re-enable proactive messages."
            self._send(sender, response, context=message.context)
        elif sub == "unmute":
            self.store.set_state("companion_muted", "false")
            response = "Companion unmuted. Proactive messages re-enabled."
            self._send(sender, response, context=message.context)
        elif sub in {"healer", "healer status", "healer dashboard"}:
            response = self._healer_dashboard()
            self._send(sender, response, context=message.context)
        elif sub in {"healer pause", "pause healer"}:
            self.store.set_state("healer_paused", "true")
            response = "Flow Healer paused. Send `system: healer resume` to continue autonomous healing."
            self._send(sender, response, context=message.context)
        elif sub in {"healer resume", "resume healer"}:
            self.store.set_state("healer_paused", "false")
            response = "Flow Healer resumed."
            self._send(sender, response, context=message.context)
        elif sub in {"healer scan", "scan healer"}:
            response = self._run_healer_scan(dry_run=False)
            self._send(sender, response, context=message.context)
            if self.healer_scan_notes_log:
                self._log_to_notes("system", sender, "healer scan", response)
        elif sub in {"healer scan dry-run", "healer scan dry run", "scan healer dry-run", "scan healer dry run"}:
            response = self._run_healer_scan(dry_run=True)
            self._send(sender, response, context=message.context)
            if self.healer_scan_notes_log:
                self._log_to_notes("system", sender, "healer scan dry-run", response)
        elif sub in ("sync office", "sync"):
            if self.office_syncer:
                try:
                    result = self.office_syncer.sync_all()
                    response = "Synced: " + ", ".join(f"{t}={n}" for t, n in result.items())
                except Exception as exc:
                    response = f"Office sync failed: {exc}"
            else:
                response = "Office sync not enabled. Set apple_flow_enable_office_sync=true and apple_flow_supabase_service_key."
            self._send(sender, response, context=message.context)
        else:
            response = (
                "Unknown system command. Use: "
                "system: stop | restart | kill provider | cancel run <run_id> | mute | unmute | "
                "healer | healer pause | healer resume | healer scan [dry-run] | sync office | "
                "teams list | team load <slug> | team current | team unload"
            )
            self._send(sender, response, context=message.context)
        return OrchestrationResult(kind=CommandKind.SYSTEM, response=response)

    def _healer_dashboard(self) -> str:
        if not hasattr(self.store, "list_healer_issues"):
            return "Flow Healer dashboard unavailable: this store backend does not expose healer state."

        states = [
            "queued",
            "claimed",
            "running",
            "verify_pending",
            "pr_pending_approval",
            "pr_open",
            "blocked",
            "failed",
            "resolved",
        ]
        issues = self.store.list_healer_issues(states=states, limit=500)
        by_state: dict[str, int] = {state: 0 for state in states}
        for issue in issues:
            state = str(issue.get("state") or "").lower()
            if state in by_state:
                by_state[state] += 1
            else:
                by_state[state] = by_state.get(state, 0) + 1

        attempts: list[dict[str, Any]] = []
        if hasattr(self.store, "list_recent_healer_attempts"):
            attempts = self.store.list_recent_healer_attempts(limit=20)
        attempt_total = len(attempts)
        failure_count = 0
        for attempt in attempts:
            state = str(attempt.get("state") or "").lower()
            if state not in {"pr_open", "resolved", "pr_pending_approval"}:
                failure_count += 1
        failure_rate = (failure_count / attempt_total) if attempt_total else 0.0

        active_locks = 0
        if hasattr(self.store, "list_healer_locks"):
            active_locks = len(self.store.list_healer_locks())

        pending = sorted(
            [issue for issue in issues if str(issue.get("state") or "") in {"queued", "claimed", "running"}],
            key=lambda item: (int(item.get("priority", 100)), str(item.get("issue_id", ""))),
        )

        lines = [
            "🩺 Flow Healer Dashboard",
            f"Paused: {'yes' if self.store.get_state('healer_paused') == 'true' else 'no'}",
            f"Total tracked issues: {len(issues)}",
            (
                "State counts: "
                f"queued={by_state.get('queued', 0)}, "
                f"running={by_state.get('running', 0)}, "
                f"verify_pending={by_state.get('verify_pending', 0)}, "
                f"pr_pending_approval={by_state.get('pr_pending_approval', 0)}, "
                f"pr_open={by_state.get('pr_open', 0)}, "
                f"blocked={by_state.get('blocked', 0)}, "
                f"failed={by_state.get('failed', 0)}, "
                f"resolved={by_state.get('resolved', 0)}"
            ),
            (
                f"Recent attempts: {attempt_total} "
                f"(failure_rate={failure_rate:.0%})"
            ),
            f"Active lock leases: {active_locks}",
        ]

        if hasattr(self.store, "get_healer_lesson_stats"):
            stats = self.store.get_healer_lesson_stats()
            total_lessons = int(stats.get("total_lessons", 0) or 0)
            recently_used = int(stats.get("recently_used", 0) or 0)
            lines.append(f"Learned lessons: {total_lessons} (recently_used={recently_used})")
            top_failure_classes = stats.get("top_failure_classes") or []
            if isinstance(top_failure_classes, list) and top_failure_classes:
                rendered = ", ".join(
                    f"{entry.get('failure_class', '?')}={entry.get('count', 0)}"
                    for entry in top_failure_classes[:3]
                    if isinstance(entry, dict)
                )
                if rendered:
                    lines.append(f"Top learned failure classes: {rendered}")

        if pending:
            lines.append("Top pending:")
            for issue in pending[:5]:
                issue_id = issue.get("issue_id", "?")
                title = str(issue.get("title") or "").strip().replace("\n", " ")
                if len(title) > 80:
                    title = f"{title[:77]}..."
                priority = issue.get("priority", "?")
                state = issue.get("state", "?")
                lines.append(f"- #{issue_id} [{state}] p={priority} {title}")
        else:
            lines.append("Top pending: none")

        lines.append("Tip: use labels `healer:ready` + `healer:pr-approved` to advance guarded PR flow.")
        return "\n".join(lines)

    def _run_healer_scan(self, *, dry_run: bool) -> str:
        if not self.healer_repo_path:
            return "Flow Healer scan unavailable: `apple_flow_healer_repo_path` is not configured."
        repo_path = Path(self.healer_repo_path).expanduser().resolve()
        if not repo_path.exists():
            return f"Flow Healer scan unavailable: repo path does not exist: {repo_path}"

        tracker = GitHubHealerTracker(repo_path=repo_path)
        scanner = FlowHealerScanner(
            repo_path=repo_path,
            store=self.store,
            tracker=tracker,
            severity_threshold=self.healer_scan_severity_threshold,
            max_issues_per_run=self.healer_scan_max_issues_per_run,
            default_labels=self.healer_scan_default_labels,
            enable_issue_creation=self.healer_scan_enable_issue_creation,
        )
        summary = scanner.run_scan(dry_run=dry_run)
        created = summary.get("created_issues") or []
        created_lines = []
        for issue in created[:5]:
            number = issue.get("number", "?")
            url = issue.get("html_url", "")
            if url:
                created_lines.append(f"- #{number}: {url}")
            else:
                created_lines.append(f"- #{number}")
        lines = [
            "🩺 Flow Healer Scan",
            f"Mode: {'dry-run' if dry_run else 'live'}",
            f"Run ID: {summary.get('run_id', '?')}",
            f"Findings: {summary.get('findings_total', 0)} total, {summary.get('findings_over_threshold', 0)} at/above threshold",
            f"Threshold: {summary.get('severity_threshold', self.healer_scan_severity_threshold)}",
            (
                f"Issues: {len(created)} created, "
                f"{summary.get('deduped_count', 0)} deduped, "
                f"{summary.get('skipped_budget_count', 0)} skipped (budget)"
            ),
        ]
        failed_checks = summary.get("failed_checks") or []
        if failed_checks:
            lines.append("Failed checks: " + ", ".join(str(item) for item in failed_checks))
        if created_lines:
            lines.append("Created issue(s):")
            lines.extend(created_lines)
        elif not dry_run:
            lines.append("Created issue(s): none")
        return "\n".join(lines)

    def _parse_team_system_command(self, subcommand: str) -> tuple[str, str, str]:
        """Return (action, slug, remainder) for supported team system commands."""
        sub = (subcommand or "").strip()
        lowered = sub.lower()

        if lowered in {"teams list", "team list", "list teams"}:
            return ("list", "", "")
        if lowered in {"team current", "current team"}:
            return ("current", "", "")
        if lowered in {"team unload", "unload team", "clear team", "reset team"}:
            return ("unload", "", "")

        if lowered.startswith("team load "):
            tail = sub[10:].strip()
        elif lowered.startswith("load team "):
            tail = sub[10:].strip()
        else:
            return ("", "", "")

        remainder = ""
        split_idx = tail.lower().find(" and ")
        if split_idx >= 0:
            slug = tail[:split_idx].strip()
            remainder = tail[split_idx + 5 :].strip()
        else:
            slug = tail.strip()
        return ("load", slug.lower(), remainder)

    def _handle_team_system(
        self,
        message: InboundMessage,
        action: str,
        slug: str,
        remainder: str,
    ) -> OrchestrationResult:
        sender = message.sender

        if not self.team_catalog.is_available():
            response = "Agent teams are not available on this host (missing `agents/catalog.toml`)."
            self._send(sender, response, context=message.context)
            return OrchestrationResult(kind=CommandKind.SYSTEM, response=response)

        if action == "list":
            teams = self.team_catalog.list_teams()
            if not teams:
                response = "No agent teams found."
            else:
                lines = ["Available agent teams:"]
                for team in teams:
                    summary = f" — {team.summary}" if team.summary else ""
                    lines.append(f"- `{team.slug}` ({team.title}){summary}")
                lines.append("")
                lines.append("Use: `system: team load <slug>`")
                response = "\n".join(lines)
            self._send(sender, response, context=message.context)
            return OrchestrationResult(kind=CommandKind.SYSTEM, response=response)

        if action == "current":
            active = self._get_active_team(sender)
            if not active:
                response = "No active team loaded for this sender."
            else:
                response = (
                    f"Active team: `{active.get('slug', '?')}` ({active.get('title', 'unknown')}). "
                    "It will auto-reset after your next `idea`, `plan`, `task`, or `project` request."
                )
            self._send(sender, response, context=message.context)
            return OrchestrationResult(kind=CommandKind.SYSTEM, response=response)

        if action == "unload":
            self._clear_active_team(sender)
            response = "Unloaded active team for this sender."
            self._send(sender, response, context=message.context)
            return OrchestrationResult(kind=CommandKind.SYSTEM, response=response)

        if action != "load":
            response = "Unsupported team system command."
            self._send(sender, response, context=message.context)
            return OrchestrationResult(kind=CommandKind.SYSTEM, response=response)

        if not slug:
            response = "Usage: `system: team load <slug>`"
            self._send(sender, response, context=message.context)
            return OrchestrationResult(kind=CommandKind.SYSTEM, response=response)

        team = self.team_catalog.get_team(slug)
        if team is None:
            suggestions = self.team_catalog.suggest(slug, limit=5)
            lines = [f"Unknown team: `{slug}`."]
            if suggestions:
                lines.append("Closest matches:")
                for item in suggestions:
                    lines.append(f"- `{item.slug}` ({item.title})")
            lines.append("")
            lines.append("Use: `system: teams list`")
            response = "\n".join(lines)
            self._send(sender, response, context=message.context)
            return OrchestrationResult(kind=CommandKind.SYSTEM, response=response)

        self._set_active_team(
            sender=sender,
            team_slug=team.slug,
            team_title=team.title,
        )

        mode_note = (
            "Using Codex team preset."
            if self._is_codex_cli_connector()
            else "Using TEAM.md fallback for this connector."
        )
        loaded_msg = (
            f"Loaded team `{team.slug}` ({team.title}). {mode_note} "
            "It will auto-reset after your next `idea`, `plan`, `task`, or `project` request."
        )
        self._send(sender, loaded_msg, context=message.context)

        if not remainder:
            return OrchestrationResult(kind=CommandKind.SYSTEM, response=loaded_msg)

        response = self._run_follow_on_after_team_load(message, remainder)
        return OrchestrationResult(kind=CommandKind.SYSTEM, response=response)

    def _run_follow_on_after_team_load(self, message: InboundMessage, remainder: str) -> str:
        parsed = parse_command(remainder)
        if parsed.kind in {CommandKind.IDEA, CommandKind.PLAN, CommandKind.TASK, CommandKind.PROJECT}:
            follow_text = remainder
        else:
            follow_text = f"plan: {remainder}"

        synthetic = InboundMessage(
            id=f"{message.id}:team:{uuid4().hex[:6]}",
            sender=message.sender,
            text=follow_text,
            received_at=datetime.now(UTC).isoformat(),
            is_from_me=False,
            context=dict(message.context or {}),
        )
        result = self.handle_message(synthetic)
        return result.response or "Follow-on request executed."

    def _mark_restart_echo_suppress(self, sender: str, text: str) -> None:
        """Persist a short-lived marker to suppress restart-message echo after reboot."""
        try:
            self.store.set_state(
                "system_restart_echo_suppress",
                json.dumps(
                    {
                        "sender": sender,
                        "text": text,
                        # launchd restart should occur quickly; keep this window tight.
                        "expires_at": time.time() + 120.0,
                    }
                ),
            )
        except Exception:
            logger.debug("Failed to persist restart echo suppress marker", exc_info=True)

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
        if self.memory_service is not None:
            try:
                canonical_context = self.memory_service.get_canonical_context()
                if self.memory_service.shadow_mode:
                    legacy_context = ""
                    if self.memory is not None:
                        legacy_context = self.memory.get_context_for_prompt()
                    self.memory_service.log_shadow_diff(
                        legacy_context=legacy_context,
                        canonical_context=canonical_context,
                    )
                    if legacy_context:
                        return f"Persistent memory context:\n{legacy_context}\n\n{prompt}"
                    if canonical_context:
                        return f"Persistent memory context:\n{canonical_context}\n\n{prompt}"
                    return prompt

                context = self.memory_service.get_context_for_prompt()
                if context:
                    return f"Persistent memory context:\n{context}\n\n{prompt}"
            except Exception:
                logger.debug("Failed to inject memory v2 context", exc_info=True)

        if self.memory is not None:
            try:
                context = self.memory.get_context_for_prompt()
                if context:
                    return f"Persistent memory context:\n{context}\n\n{prompt}"
            except Exception:
                logger.debug("Failed to inject legacy memory context", exc_info=True)
        return prompt

    # --- Attachment Context ---

    def _prepare_attachment_context(self, message: InboundMessage) -> None:
        if not self.enable_attachments or self.attachment_processor is None:
            return
        attachments = message.context.get("attachments", [])
        if not attachments:
            return
        block, metadata = self.attachment_processor.build_prompt_block(message.id, attachments)
        if block:
            message.context["attachment_prompt_block"] = block
        if metadata:
            message.context["attachment_processing"] = metadata

    def _inject_attachment_context(self, message: InboundMessage, prompt: str) -> str:
        if not self.enable_attachments:
            return prompt
        block = str(message.context.get("attachment_prompt_block") or "").strip()
        if block:
            return f"{prompt}\n\n{block}"
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

    def _run_non_mutating_turn(
        self,
        *,
        sender: str,
        thread_id: str,
        prompt: str,
        context: dict[str, Any] | None = None,
        team_context: dict[str, Any] | None = None,
        allow_tools: bool = True,
        cwd: str | None = None,
    ) -> str:
        if self.enable_progress_streaming and hasattr(self.connector, "run_turn_streaming"):
            return self._run_non_mutating_with_progress(
                sender=sender,
                thread_id=thread_id,
                prompt=prompt,
                context=context,
                team_context=team_context,
                allow_tools=allow_tools,
                cwd=cwd,
            )
        return self._run_non_mutating_with_heartbeat(
            sender=sender,
            runner=lambda: self._run_connector_turn(
                thread_id,
                prompt,
                team_context=team_context,
                allow_tools=allow_tools,
                cwd=cwd,
            ),
            context=context,
        )

    def _run_non_mutating_with_progress(
        self,
        *,
        sender: str,
        thread_id: str,
        prompt: str,
        context: dict[str, Any] | None = None,
        team_context: dict[str, Any] | None = None,
        allow_tools: bool = True,
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
            if preview and (now - last_update) >= self._approval.progress_update_interval_seconds:
                self._send(sender, f"[Progress] {preview}", context=context)
                last_update = now

        return self._run_non_mutating_with_heartbeat(
            sender=sender,
            runner=lambda: self._run_connector_turn_streaming(
                thread_id,
                prompt,
                on_progress,
                team_context=team_context,
                allow_tools=allow_tools,
                cwd=cwd,
            ),
            context=context,
            progress_state=progress_state,
        )

    def _run_non_mutating_with_heartbeat(
        self,
        *,
        sender: str,
        runner: Callable[[], str],
        context: dict[str, Any] | None = None,
        progress_state: dict[str, Any] | None = None,
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

        while not done.wait(timeout=self._approval.execution_heartbeat_seconds):
            now = time.monotonic()
            elapsed = int(now - start)
            detail = "no streamed output yet"
            if progress_state:
                last_output = progress_state.get("last_output_monotonic")
                last_snippet = str(progress_state.get("last_snippet") or "")
                if isinstance(last_output, (int, float)):
                    stale_for = max(0, int(now - float(last_output)))
                    if last_snippet:
                        detail = f"last output {stale_for}s ago: {last_snippet}"
            self._send(
                sender,
                f"⏳ Still working (chat) — {elapsed}s elapsed; {detail}.",
                context=context,
            )

        if "exc" in error:
            raise error["exc"]

        return result.get("output", "")

    def _is_codex_cli_connector(self) -> bool:
        return self.connector.__class__.__name__ == "CodexCliConnector"

    def _team_state_key(self, sender: str) -> str:
        return f"active_team:{normalize_sender(sender)}"

    def _set_active_team(self, sender: str, team_slug: str, team_title: str) -> None:
        state = {
            "slug": team_slug,
            "title": team_title,
            "mode": "one_shot",
            "armed_at": datetime.now(UTC).isoformat(),
        }
        self.store.set_state(self._team_state_key(sender), json.dumps(state))

    def _get_active_team(self, sender: str) -> dict[str, Any] | None:
        raw = self.store.get_state(self._team_state_key(sender))
        if not raw:
            return None
        try:
            state = json.loads(raw)
        except Exception:
            return None
        if not isinstance(state, dict):
            return None
        slug = str(state.get("slug", "")).strip().lower()
        if not slug:
            return None
        title = str(state.get("title", slug)).strip()
        return {"slug": slug, "title": title, "mode": "one_shot"}

    def _consume_active_team(self, sender: str) -> None:
        self._clear_active_team(sender)

    def _clear_active_team(self, sender: str) -> None:
        self.store.set_state(self._team_state_key(sender), "")

    def _build_turn_team_context(self, active_team: dict[str, Any] | None) -> dict[str, Any] | None:
        if not active_team:
            return None

        slug = str(active_team.get("slug", "")).strip().lower()
        if not slug:
            return None

        team = self.team_catalog.get_team(slug)
        if team is None:
            return None

        context: dict[str, Any] = {"slug": team.slug, "title": team.title}
        if self._is_codex_cli_connector() and team.preset_path.exists():
            context["codex_config_path"] = str(team.preset_path)
            return context

        fallback = self.team_catalog.build_team_prompt_fallback(team.slug)
        if fallback:
            context["prompt_fallback"] = fallback
        return context

    def _apply_team_prompt_fallback(self, prompt: str, team_context: dict[str, Any] | None) -> str:
        if not team_context:
            return prompt
        fallback = str(team_context.get("prompt_fallback", "")).strip()
        if not fallback:
            return prompt
        return f"{fallback}\n\n{prompt}"

    def _is_workspace_allowed(self, candidate: str) -> bool:
        target = Path(candidate).resolve()
        for allowed_path in self._allowed_workspace_set:
            if allowed_path == target or allowed_path in target.parents:
                return True
        return False

    def _resolve_file_aliases(self, payload: str) -> tuple[str, list[tuple[str, str]], list[str]]:
        """Resolve inline @f:<alias> tokens to validated absolute file paths.

        Returns (rewritten_payload, resolved_mappings, warnings).
        """
        if not payload or "@f:" not in payload:
            return payload, [], []

        resolved_by_alias: dict[str, str | None] = {}
        resolved_pairs: list[tuple[str, str]] = []
        seen_resolved: set[str] = set()
        warnings: list[str] = []
        seen_warnings: set[str] = set()

        def _warn_once(message: str) -> None:
            if message in seen_warnings:
                return
            seen_warnings.add(message)
            warnings.append(message)

        def _resolve(alias: str) -> str | None:
            if alias in resolved_by_alias:
                return resolved_by_alias[alias]

            configured = str(self.file_aliases.get(alias) or "").strip()
            if not configured:
                _warn_once(f"@f:{alias} is not configured.")
                resolved_by_alias[alias] = None
                return None

            target = Path(configured).expanduser().resolve()
            if not target.exists() or not target.is_file():
                _warn_once(f"@f:{alias} target missing file: {target}")
                resolved_by_alias[alias] = None
                return None
            if not self._is_workspace_allowed(str(target)):
                _warn_once(f"@f:{alias} is outside allowed_workspaces: {target}")
                resolved_by_alias[alias] = None
                return None

            resolved_path = str(target)
            resolved_by_alias[alias] = resolved_path
            if alias not in seen_resolved:
                seen_resolved.add(alias)
                resolved_pairs.append((alias, resolved_path))
            return resolved_path

        def _replace(match: re.Match[str]) -> str:
            alias = match.group(1)
            resolved = _resolve(alias)
            if resolved:
                return resolved
            return match.group(0)

        rewritten = _FILE_ALIAS_RE.sub(_replace, payload)
        return rewritten, resolved_pairs, warnings

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
