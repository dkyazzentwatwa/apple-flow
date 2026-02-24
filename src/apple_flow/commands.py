from __future__ import annotations

import json
import logging
import re
import subprocess
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from .commanding import CommandKind, ParsedCommand
from .models import InboundMessage

if TYPE_CHECKING:
    from .orchestrator import RelayOrchestrator

logger = logging.getLogger("apple_flow.commands")

class CommandHandler(ABC):
    @abstractmethod
    def handle(self, orchestrator: RelayOrchestrator, message: InboundMessage, command: ParsedCommand) -> str:
        pass

class HealthCommandHandler(CommandHandler):
    def handle(self, orchestrator: RelayOrchestrator, message: InboundMessage, command: ParsedCommand) -> str:
        parts = ["Apple Flow Health"]

        if hasattr(orchestrator.store, "get_stats"):
            stats = orchestrator.store.get_stats()
            parts.append(f"Sessions: {stats.get('active_sessions', '?')}")
            parts.append(f"Messages processed: {stats.get('total_messages', '?')}")
            parts.append(f"Pending approvals: {stats.get('pending_approvals', '?')}")
            runs = stats.get("runs_by_state", {})
            if runs:
                runs_str = ", ".join(f"{state}: {count}" for state, count in sorted(runs.items()))
                parts.append(f"Runs: {runs_str}")
        else:
            pending = orchestrator.store.list_pending_approvals()
            parts.append(f"Pending approvals: {len(pending)}")

        started_at = orchestrator.store.get_state("daemon_started_at")
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

        companion_last_check = orchestrator.store.get_state("companion_last_check_at")
        if companion_last_check:
            try:
                check_dt = datetime.fromisoformat(companion_last_check)
                minutes_ago = int((datetime.now() - check_dt).total_seconds() / 60)
                obs_count = orchestrator.store.get_state("companion_last_obs_count") or "?"
                skip_reason = orchestrator.store.get_state("companion_last_skip_reason") or ""
                sent_at = orchestrator.store.get_state("companion_last_sent_at")
                hour_count = orchestrator.store.get_state("companion_proactive_hour_count") or "0"
                muted = orchestrator.store.get_state("companion_muted") == "true"

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
        orchestrator.egress.send(message.sender, response)
        return response

class HistoryCommandHandler(CommandHandler):
    def handle(self, orchestrator: RelayOrchestrator, message: InboundMessage, command: ParsedCommand) -> str:
        query = command.payload
        if query and hasattr(orchestrator.store, "search_messages"):
            results = orchestrator.store.search_messages(message.sender, query, limit=10)
            if not results:
                response = f"No messages found matching '{query}'."
            else:
                lines = [f"Messages matching '{query}' ({len(results)} found):"]
                for msg in results:
                    text_preview = (msg.get("text", ""))[:80]
                    received = msg.get("received_at", "?")
                    lines.append(f"  [{received}] {text_preview}")
                response = "\n".join(lines)
        elif hasattr(orchestrator.store, "recent_messages"):
            results = orchestrator.store.recent_messages(message.sender, limit=10)
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

        orchestrator.egress.send(message.sender, response)
        return response

class UsageCommandHandler(CommandHandler):
    def handle(self, orchestrator: RelayOrchestrator, message: InboundMessage, command: ParsedCommand) -> str:
        sub = command.payload.lower().strip()

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
            orchestrator.egress.send(message.sender, response)
            return response
        except (json.JSONDecodeError, FileNotFoundError, Exception) as exc:
            response = f"Usage data unavailable: {exc}"
            orchestrator.egress.send(message.sender, response)
            return response

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
        orchestrator.egress.send(message.sender, response)
        return response

class LogsCommandHandler(CommandHandler):
    _ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

    def handle(self, orchestrator: RelayOrchestrator, message: InboundMessage, command: ParsedCommand) -> str:
        from pathlib import Path
        n = 20
        payload = command.payload
        if payload.strip():
            try:
                requested = int(payload.strip())
                n = max(1, min(requested, 50))
            except ValueError:
                pass

        log_path: Path | None = None
        if orchestrator.log_file_path:
            candidate = Path(orchestrator.log_file_path)
            if not candidate.is_absolute():
                # Resolve relative to repo root (two levels above this file)
                candidate = Path(__file__).resolve().parents[2] / orchestrator.log_file_path
            if candidate.exists():
                log_path = candidate

        if log_path is None:
            response = f"Log file not found: {orchestrator.log_file_path or '(not configured)'}"
        else:
            try:
                raw_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                tail = raw_lines[-n:] if len(raw_lines) >= n else raw_lines
                clean = [self._ANSI_ESCAPE.sub("", line) for line in tail]
                response = f"Last {len(clean)} lines of {log_path.name}:\n" + "\n".join(clean)
            except OSError as exc:
                response = f"Could not read log file: {exc}"

        orchestrator.egress.send(message.sender, response)
        return response

class SystemCommandHandler(CommandHandler):
    def handle(self, orchestrator: RelayOrchestrator, message: InboundMessage, command: ParsedCommand) -> str:
        sub = command.payload.strip().lower()
        if sub == "stop":
            response = "Apple Flow shutting down..."
            orchestrator.egress.send(message.sender, response)
            if orchestrator.shutdown_callback is not None:
                orchestrator.shutdown_callback()
        elif sub == "restart":
            response = "Apple Flow restarting... (text 'health' to confirm it's back)"
            orchestrator.egress.send(message.sender, response)
            try:
                subprocess.run(["launchctl", "stop", "local.apple-flow"], check=False, timeout=5)
            except Exception as exc:
                logger.warning("Failed to trigger launchctl restart: %s", exc)
            if orchestrator.shutdown_callback is not None:
                orchestrator.shutdown_callback()
        elif sub == "mute":
            orchestrator.store.set_state("companion_muted", "true")
            response = "Companion muted. Send 'system: unmute' to re-enable proactive messages."
            orchestrator.egress.send(message.sender, response)
        elif sub == "unmute":
            orchestrator.store.set_state("companion_muted", "false")
            response = "Companion unmuted. Proactive messages re-enabled."
            orchestrator.egress.send(message.sender, response)
        elif sub in ("sync office", "sync"):
            if orchestrator.office_syncer:
                try:
                    result = orchestrator.office_syncer.sync_all()
                    response = "Synced: " + ", ".join(f"{t}={n}" for t, n in result.items())
                except Exception as exc:
                    response = f"Office sync failed: {exc}"
            else:
                response = "Office sync not enabled. Set apple_flow_enable_office_sync=true and apple_flow_supabase_service_key."
            orchestrator.egress.send(message.sender, response)
        else:
            response = "Unknown system command. Use: system: stop | restart | mute | unmute | sync office"
            orchestrator.egress.send(message.sender, response)
        return response

class StatusCommandHandler(CommandHandler):
    def handle(self, orchestrator: RelayOrchestrator, message: InboundMessage, command: ParsedCommand) -> str:
        pending = orchestrator.store.list_pending_approvals()
        if not pending:
            response = "No pending approvals."
        else:
            lines = [f"Pending approvals ({len(pending)}):"]
            for req in pending:
                req_id = req.get("request_id", "?")
                preview = req.get("command_preview", "")[:80].replace("\n", " ")
                lines.append(f"\n{req_id}")
                lines.append(f"  {preview}")
            lines.append("\nReply `approve <id>` or `deny <id>` to act on one.")
            lines.append("Reply `deny all` to cancel all.")
            response = "\n".join(lines)
        orchestrator.egress.send(message.sender, response)
        return response

class DenyAllCommandHandler(CommandHandler):
    def handle(self, orchestrator: RelayOrchestrator, message: InboundMessage, command: ParsedCommand) -> str:
        if not hasattr(orchestrator.store, "deny_all_approvals"):
            response = "deny all not supported by this store."
        else:
            count = orchestrator.store.deny_all_approvals()
            response = f"Cancelled {count} pending approval{'s' if count != 1 else ''}." if count else "No pending approvals to cancel."
        orchestrator.egress.send(message.sender, response)
        return response

class ClearContextCommandHandler(CommandHandler):
    def handle(self, orchestrator: RelayOrchestrator, message: InboundMessage, command: ParsedCommand) -> str:
        if hasattr(orchestrator.connector, "reset_thread"):
            thread_id = orchestrator.connector.reset_thread(message.sender)
        else:
            thread_id = orchestrator.connector.get_or_create_thread(message.sender)
        orchestrator.store.upsert_session(message.sender, thread_id, CommandKind.CHAT.value)
        response = "Started a fresh chat context for this sender."
        orchestrator.egress.send(message.sender, response)
        return response

COMMAND_HANDLERS: dict[CommandKind, CommandHandler] = {
    CommandKind.HEALTH: HealthCommandHandler(),
    CommandKind.HISTORY: HistoryCommandHandler(),
    CommandKind.USAGE: UsageCommandHandler(),
    CommandKind.LOGS: LogsCommandHandler(),
    CommandKind.SYSTEM: SystemCommandHandler(),
    CommandKind.STATUS: StatusCommandHandler(),
    CommandKind.DENY_ALL: DenyAllCommandHandler(),
    CommandKind.CLEAR_CONTEXT: ClearContextCommandHandler(),
}
