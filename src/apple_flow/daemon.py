from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import signal
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .ambient import AmbientScanner
from .calendar_egress import AppleCalendarEgress
from .calendar_ingress import AppleCalendarIngress
from .claude_cli_connector import ClaudeCliConnector
from .cline_connector import ClineConnector
from .codex_cli_connector import CodexCliConnector
from .commanding import CommandKind, parse_command
from .companion import CompanionLoop
from .config import RelaySettings
from .egress import IMessageEgress
from .gateway_setup import ensure_gateway_resources
from .gemini_cli_connector import GeminiCliConnector
from .ingress import IMessageIngress
from .kilo_cli_connector import KiloCliConnector
from .mail_egress import AppleMailEgress
from .mail_ingress import AppleMailIngress
from .memory import FileMemory
from .memory_v2 import MemoryService
from .notes_egress import AppleNotesEgress
from .notes_ingress import AppleNotesIngress
from .office_sync import OfficeSyncer
from .orchestrator import RelayOrchestrator
from .policy import PolicyEngine
from .protocols import ConnectorProtocol
from .reminders_egress import AppleRemindersEgress
from .reminders_ingress import AppleRemindersIngress
from .run_executor import RunExecutor
from .scheduler import FollowUpScheduler
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.daemon")

_FASTLANE_COMMANDS = {
    CommandKind.HELP,
    CommandKind.STATUS,
    CommandKind.HEALTH,
    CommandKind.HISTORY,
    CommandKind.USAGE,
    CommandKind.LOGS,
    CommandKind.DENY,
    CommandKind.DENY_ALL,
    CommandKind.CLEAR_CONTEXT,
    CommandKind.SYSTEM,
}


def _normalize_echo_text(text: str) -> str:
    normalized = (text or "")
    normalized = normalized.replace("\u2019", "'").replace("\u2018", "'")
    normalized = normalized.replace('"', "'")
    return " ".join(normalized.lower().split())


def migrate_legacy_db_if_needed(
    settings: RelaySettings,
    *,
    legacy_db_path: Path | None = None,
    default_db_path: Path | None = None,
) -> bool:
    """Move legacy DB path to the new default location when it is safe to do so."""
    legacy_db_path = legacy_db_path or (Path.home() / ".codex" / "relay.db")
    default_db_path = default_db_path or (Path.home() / ".apple-flow" / "relay.db")
    if "db_path" in settings.model_fields_set:
        return False
    target_db_path = Path(settings.db_path)
    if target_db_path != default_db_path:
        return False
    if target_db_path.exists() or not legacy_db_path.exists():
        return False

    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(legacy_db_path), str(target_db_path))
        logger.info("Migrated legacy DB from %s to %s", legacy_db_path, target_db_path)
        return True
    except OSError as exc:
        logger.warning(
            "Could not migrate legacy DB from %s to %s: %s",
            legacy_db_path,
            target_db_path,
            exc,
        )
        return False


def gateway_resource_statuses_for_settings(settings: RelaySettings):
    return ensure_gateway_resources(
        enable_reminders=settings.enable_reminders_polling,
        enable_notes=settings.enable_notes_polling,
        enable_notes_logging=settings.enable_notes_logging,
        enable_calendar=settings.enable_calendar_polling,
        reminders_list_name=settings.reminders_list_name,
        reminders_archive_list_name=settings.reminders_archive_list_name,
        notes_folder_name=settings.notes_folder_name,
        notes_archive_folder_name=settings.notes_archive_folder_name,
        notes_log_folder_name=settings.notes_log_folder_name,
        calendar_name=settings.calendar_name,
    )


class RelayDaemon:
    def __init__(self, settings: RelaySettings):
        self.settings = settings
        self._ensure_gateway_resources()
        self.store = SQLiteStore(Path(settings.db_path))
        self.store.bootstrap()
        self.policy = PolicyEngine(settings)
        self.ingress = IMessageIngress(
            settings.messages_db_path,
            enable_attachments=settings.enable_attachments,
            max_attachment_size_mb=settings.max_attachment_size_mb,
        )
        self.egress = IMessageEgress(
            suppress_duplicate_outbound_seconds=settings.suppress_duplicate_outbound_seconds
        )

        # Choose connector based on configuration
        for warning in settings.get_connector_warnings():
            logger.warning(warning)
        connector_type = settings.get_connector_type()
        known_connectors = {
            "codex-cli",
            "claude-cli",
            "gemini-cli",
            "kilo-cli",
            "cline",
        }
        if connector_type not in known_connectors:
            raise ValueError(
                f"Unknown connector type: {connector_type!r}. "
                f"Valid options: {', '.join(sorted(known_connectors))}"
            )

        if connector_type == "claude-cli":
            logger.info("Using Claude CLI connector (claude -p) for stateless execution")
            self.connector = ClaudeCliConnector(
                claude_command=settings.claude_cli_command,
                workspace=settings.default_workspace,
                timeout=settings.codex_turn_timeout_seconds,
                context_window=settings.claude_cli_context_window,
                model=settings.claude_cli_model,
                dangerously_skip_permissions=settings.claude_cli_dangerously_skip_permissions,
                tools=settings.claude_cli_tools,
                allowed_tools=settings.claude_cli_allowed_tools,
                inject_tools_context=settings.inject_tools_context,
                system_prompt=settings.personality_prompt.replace(
                    "{workspace}", settings.default_workspace
                ),
            )
        elif connector_type == "cline":
            logger.info("Using Cline CLI connector (cline -y) for agentic execution")
            self.connector = ClineConnector(
                cline_command=settings.cline_command,
                workspace=settings.default_workspace,
                timeout=settings.codex_turn_timeout_seconds,
                context_window=settings.cline_context_window,
                model=settings.cline_model,
                use_json=settings.cline_use_json,
                act_mode=settings.cline_act_mode,
            )
        elif connector_type == "gemini-cli":
            logger.info("Using Gemini CLI connector (gemini -p) for stateless execution")
            self.connector = GeminiCliConnector(
                gemini_command=settings.gemini_cli_command,
                workspace=settings.default_workspace,
                timeout=settings.codex_turn_timeout_seconds,
                context_window=settings.gemini_cli_context_window,
                model=settings.gemini_cli_model,
                approval_mode=settings.gemini_cli_approval_mode,
                inject_tools_context=settings.inject_tools_context,
                system_prompt=settings.personality_prompt.replace(
                    "{workspace}", settings.default_workspace
                ),
            )
        elif connector_type == "kilo-cli":
            logger.info("Using Kilo CLI connector (kilo run) for stateless execution")
            self.connector = KiloCliConnector(
                kilo_command=settings.kilo_cli_command,
                workspace=settings.default_workspace,
                timeout=settings.codex_turn_timeout_seconds,
                context_window=settings.kilo_cli_context_window,
                model=settings.kilo_cli_model,
                inject_tools_context=settings.inject_tools_context,
                system_prompt=settings.personality_prompt.replace(
                    "{workspace}", settings.default_workspace
                ),
            )
        else:  # codex-cli (default)
            logger.info("Using CLI connector (codex exec) for stateless execution")
            self.connector = CodexCliConnector(
                codex_command=settings.codex_cli_command,
                workspace=settings.default_workspace,
                timeout=settings.codex_turn_timeout_seconds,
                context_window=settings.codex_cli_context_window,
                model=settings.codex_cli_model,
                inject_tools_context=settings.inject_tools_context,
            )

        # Read SOUL.md for companion identity
        self._soul_prompt = ""
        soul_path = Path(settings.soul_file)
        if not soul_path.is_absolute():
            soul_path = Path(__file__).resolve().parents[2] / settings.soul_file
        if soul_path.exists():
            try:
                self._soul_prompt = soul_path.read_text(encoding="utf-8").strip()
                logger.info("Loaded SOUL.md from %s (%d chars)", soul_path, len(self._soul_prompt))
            except Exception as exc:
                logger.warning("Failed to read SOUL.md at %s: %s", soul_path, exc)
        else:
            logger.info("SOUL.md not found at %s — using personality_prompt fallback", soul_path)

        # Inject soul prompt into connector when supported by connector implementation.
        if self._soul_prompt and hasattr(self.connector, "set_soul_prompt"):
            self.connector.set_soul_prompt(self._soul_prompt)

        # Resolve agent-office path for companion/memory
        self._office_path = soul_path.parent if self._soul_prompt else None

        # File-based memory (reads/writes agent-office MEMORY.md + 60_memory/)
        self.memory: FileMemory | None = None
        if settings.enable_memory and self._office_path:
            self.memory = FileMemory(self._office_path, max_context_chars=settings.memory_max_context_chars)
            logger.info("File-based memory enabled (office=%s)", self._office_path)

        # Canonical memory v2 (active or shadow mode)
        self.memory_service: MemoryService | None = None
        if settings.enable_memory and self._office_path and (
            settings.enable_memory_v2 or settings.memory_v2_shadow_mode
        ):
            db_path = (
                Path(settings.memory_v2_db_path).expanduser()
                if settings.memory_v2_db_path.strip()
                else self._office_path / ".apple-flow-memory.sqlite3"
            )
            if not db_path.is_absolute():
                db_path = (Path(__file__).resolve().parents[2] / db_path).resolve()
            self.memory_service = MemoryService(
                office_path=self._office_path,
                db_path=db_path,
                max_context_chars=settings.memory_max_context_chars,
                enabled=settings.enable_memory_v2,
                shadow_mode=settings.memory_v2_shadow_mode,
                max_storage_mb=settings.memory_max_storage_mb,
                include_legacy_fallback=settings.memory_v2_include_legacy_fallback,
                default_scope=settings.memory_v2_scope,
            )
            if settings.memory_v2_migrate_on_start:
                self.memory_service.backfill_from_legacy()
            logger.info(
                "Canonical memory v2 initialized (enabled=%s, shadow=%s, db=%s)",
                settings.enable_memory_v2,
                settings.memory_v2_shadow_mode,
                db_path,
            )

        # Follow-up scheduler (SQLite-backed)
        self.scheduler: FollowUpScheduler | None = None
        if settings.enable_follow_ups:
            self.scheduler = FollowUpScheduler(self.store)
            logger.info("Follow-up scheduler enabled")

        # Office syncer (agent-office → Supabase)
        self.office_syncer: OfficeSyncer | None = None
        if settings.enable_office_sync and settings.supabase_service_key and self._office_path:
            self.office_syncer = OfficeSyncer(
                office_path=self._office_path,
                supabase_url=settings.supabase_url,
                service_key=settings.supabase_service_key,
            )
            logger.info(
                "Office sync enabled (url=%s, office=%s, interval=%.0fs)",
                settings.supabase_url,
                self._office_path,
                settings.office_sync_interval_seconds,
            )

        # Companion loop (proactive observations + daily digest)
        self.companion: CompanionLoop | None = None
        if settings.enable_companion:
            owner = settings.allowed_senders[0] if settings.allowed_senders else ""
            if owner:
                self.companion = CompanionLoop(
                    connector=self.connector,
                    egress=self.egress,
                    store=self.store,
                    owner=owner,
                    soul_prompt=self._soul_prompt,
                    office_path=self._office_path,
                    config=settings,
                    scheduler=self.scheduler,
                    memory=self.memory,
                    syncer=self.office_syncer,
                )
                logger.info("Companion loop enabled (owner=%s, poll=%.0fs)", owner, settings.companion_poll_interval_seconds)
            else:
                logger.warning("Companion enabled but no allowed_senders configured — skipping")

        # Ambient scanner (passive context enrichment)
        self.ambient: AmbientScanner | None = None
        if settings.enable_ambient_scanning and self.memory:
            self.ambient = AmbientScanner(
                memory=self.memory,
                scan_interval_seconds=settings.ambient_scan_interval_seconds,
            )
            logger.info("Ambient scanner enabled (interval=%.0fs)", settings.ambient_scan_interval_seconds)

        # Create channel-specific egress objects first so they can be passed to main orchestrator
        # (for post-execution cleanup after approval)
        reminders_egress_obj = None
        notes_egress_obj = None
        calendar_egress_obj = None

        if settings.enable_reminders_polling:
            reminders_egress_obj = AppleRemindersEgress(list_name=settings.reminders_list_name)
        if settings.enable_notes_polling:
            notes_egress_obj = AppleNotesEgress(folder_name=settings.notes_folder_name)
        if settings.enable_calendar_polling:
            calendar_egress_obj = AppleCalendarEgress(calendar_name=settings.calendar_name)

        # Notes logging egress (write-only, independent of notes polling)
        notes_log_egress_obj = None
        if settings.enable_notes_logging:
            notes_log_egress_obj = AppleNotesEgress(folder_name=settings.notes_log_folder_name)
            logger.info("Notes logging enabled (folder=%r)", settings.notes_log_folder_name)

        # Shared orchestrator params
        workspace_aliases = settings.get_workspace_aliases()
        orchestrator_kwargs = dict(
            connector=self.connector,
            store=self.store,
            allowed_workspaces=settings.allowed_workspaces,
            default_workspace=settings.default_workspace,
            approval_ttl_minutes=settings.approval_ttl_minutes,
            chat_prefix=settings.chat_prefix,
            workspace_aliases=workspace_aliases,
            auto_context_messages=settings.auto_context_messages,
            enable_progress_streaming=settings.enable_progress_streaming,
            progress_update_interval_seconds=settings.progress_update_interval_seconds,
            execution_heartbeat_seconds=settings.execution_heartbeat_seconds,
            checkpoint_on_timeout=settings.checkpoint_on_timeout,
            auto_resume_on_timeout=settings.auto_resume_on_timeout,
            max_resume_attempts=settings.max_resume_attempts,
            enable_verifier=settings.enable_verifier,
            enable_attachments=settings.enable_attachments,
            personality_prompt=settings.personality_prompt,
            shutdown_callback=self.request_shutdown,
            log_notes_egress=notes_log_egress_obj,
            notes_log_folder_name=settings.notes_log_folder_name,
            memory=self.memory,
            memory_service=self.memory_service,
            scheduler=self.scheduler,
            run_executor=None,
            office_syncer=self.office_syncer,
            log_file_path=settings.log_file_path,
        )

        self.orchestrator = RelayOrchestrator(
            egress=self.egress,
            require_chat_prefix=settings.require_chat_prefix,
            reminders_egress=reminders_egress_obj,
            reminders_archive_list_name=settings.reminders_archive_list_name,
            notes_egress=notes_egress_obj,
            notes_archive_folder_name=settings.notes_archive_folder_name,
            calendar_egress=calendar_egress_obj,
            **orchestrator_kwargs,
        )

        # Apple Mail integration (optional second ingress channel)
        self.mail_ingress: AppleMailIngress | None = None
        self.mail_egress: AppleMailEgress | None = None
        self.mail_orchestrator: RelayOrchestrator | None = None
        self._mail_owner: str = ""
        if settings.enable_mail_polling:
            logger.info(
                "Apple Mail polling enabled (account=%r, mailbox=%r, allowed_senders=%s)",
                settings.mail_poll_account or "(all)",
                settings.mail_poll_mailbox,
                len(settings.mail_allowed_senders),
            )
            self.mail_ingress = AppleMailIngress(
                account=settings.mail_poll_account,
                mailbox=settings.mail_poll_mailbox,
                max_age_days=settings.mail_max_age_days,
                trigger_tag=settings.trigger_tag,
            )
            self.mail_egress = AppleMailEgress(
                from_address=settings.mail_from_address,
                response_subject=settings.mail_response_subject,
                signature=settings.mail_signature,
            )
            self._mail_owner = settings.allowed_senders[0] if settings.allowed_senders else ""
            self.mail_orchestrator = RelayOrchestrator(
                egress=self.mail_egress,
                require_chat_prefix=settings.require_chat_prefix,
                approval_sender_override=self._mail_owner,
                **orchestrator_kwargs,
            )

        # Apple Reminders integration (optional task-queue ingress)
        self.reminders_ingress: AppleRemindersIngress | None = None
        self.reminders_egress: AppleRemindersEgress | None = reminders_egress_obj
        self.reminders_orchestrator: RelayOrchestrator | None = None
        if settings.enable_reminders_polling:
            owner = settings.reminders_owner
            if not owner and settings.allowed_senders:
                owner = settings.allowed_senders[0]
            logger.info(
                "Apple Reminders polling enabled (list=%r, owner=%s, auto_approve=%s)",
                settings.reminders_list_name,
                owner or "(unset)",
                settings.reminders_auto_approve,
            )
            self.reminders_ingress = AppleRemindersIngress(
                list_name=settings.reminders_list_name,
                owner_sender=owner,
                auto_approve=settings.reminders_auto_approve,
                trigger_tag=settings.trigger_tag,
                due_delay_seconds=settings.reminders_due_delay_seconds,
                timezone_name=settings.timezone,
                store=self.store,
            )
            self.reminders_orchestrator = RelayOrchestrator(
                egress=self.egress,
                require_chat_prefix=False,
                **orchestrator_kwargs,
            )

        # Apple Notes integration (optional long-form ingress)
        self.notes_ingress: AppleNotesIngress | None = None
        self.notes_egress: AppleNotesEgress | None = notes_egress_obj
        self.notes_orchestrator: RelayOrchestrator | None = None
        if settings.enable_notes_polling:
            notes_owner = settings.notes_owner
            if not notes_owner and settings.allowed_senders:
                notes_owner = settings.allowed_senders[0]
            logger.info(
                "Apple Notes polling enabled (folder=%r, trigger_tag=%r, owner=%s)",
                settings.notes_folder_name,
                settings.trigger_tag,
                notes_owner or "(unset)",
            )
            self.notes_ingress = AppleNotesIngress(
                folder_name=settings.notes_folder_name,
                trigger_tag=settings.trigger_tag,
                owner_sender=notes_owner,
                auto_approve=settings.notes_auto_approve,
                fetch_timeout_seconds=settings.notes_fetch_timeout_seconds,
                fetch_retries=settings.notes_fetch_retries,
                fetch_retry_delay_seconds=settings.notes_fetch_retry_delay_seconds,
                store=self.store,
            )
            self.notes_orchestrator = RelayOrchestrator(
                egress=self.egress,
                require_chat_prefix=False,
                **orchestrator_kwargs,
            )

        # Apple Calendar integration (optional scheduled-task ingress)
        self.calendar_ingress: AppleCalendarIngress | None = None
        self.calendar_egress: AppleCalendarEgress | None = calendar_egress_obj
        self.calendar_orchestrator: RelayOrchestrator | None = None
        if settings.enable_calendar_polling:
            cal_owner = settings.calendar_owner
            if not cal_owner and settings.allowed_senders:
                cal_owner = settings.allowed_senders[0]
            logger.info(
                "Apple Calendar polling enabled (calendar=%r, owner=%s, lookahead=%dm)",
                settings.calendar_name,
                cal_owner or "(unset)",
                settings.calendar_lookahead_minutes,
            )
            self.calendar_ingress = AppleCalendarIngress(
                calendar_name=settings.calendar_name,
                owner_sender=cal_owner,
                auto_approve=settings.calendar_auto_approve,
                lookahead_minutes=settings.calendar_lookahead_minutes,
                trigger_tag=settings.trigger_tag,
                store=self.store,
            )
            self.calendar_orchestrator = RelayOrchestrator(
                egress=self.egress,
                require_chat_prefix=False,
                **orchestrator_kwargs,
            )

        # Durable async run executor (approvals enqueue long execution jobs).
        self.run_executor = RunExecutor(
            store=self.store,
            approval_handler=self.orchestrator._approval,
            worker_count=settings.run_worker_count,
            lease_seconds=settings.run_job_lease_seconds,
            recovery_scan_seconds=settings.run_recovery_scan_seconds,
        )
        self.orchestrator.set_run_executor(self.run_executor)
        if self.mail_orchestrator is not None:
            self.mail_orchestrator.set_run_executor(self.run_executor)
        if self.reminders_orchestrator is not None:
            self.reminders_orchestrator.set_run_executor(self.run_executor)
        if self.notes_orchestrator is not None:
            self.notes_orchestrator.set_run_executor(self.run_executor)
        if self.calendar_orchestrator is not None:
            self.calendar_orchestrator.set_run_executor(self.run_executor)

        self._concurrency_sem = asyncio.Semaphore(settings.max_concurrent_ai_calls)
        self._inflight_dispatch_tasks: set[asyncio.Task] = set()
        self._inflight_mail_ids: set[str] = set()

        persisted_cursor = self.store.get_state("last_rowid")
        self._last_rowid: int | None = int(persisted_cursor) if persisted_cursor is not None else None
        self._last_messages_db_error_at: float = 0.0
        self._last_state_db_error_at: float = 0.0
        self._shutdown_requested = False
        latest = self.ingress.latest_rowid()
        if latest is not None and not self.settings.process_historical_on_first_start:
            if self._last_rowid is None:
                self._last_rowid = latest
                self.store.set_state("last_rowid", str(latest))
                logger.info("Initialized cursor to latest rowid=%s to avoid replaying historical messages.", latest)
            elif (latest - self._last_rowid) > max(0, self.settings.max_startup_replay_rows):
                logger.info(
                    "Fast-forwarding stale cursor from rowid=%s to latest rowid=%s (backlog=%s > max_startup_replay_rows=%s).",
                    self._last_rowid,
                    latest,
                    latest - self._last_rowid,
                    self.settings.max_startup_replay_rows,
                )
                self._last_rowid = latest
                self.store.set_state("last_rowid", str(latest))

        # Record daemon start time for health dashboard and startup catch-up window
        self._startup_time = datetime.now(UTC)
        self.store.set_state("daemon_started_at", self._startup_time.isoformat())

    def _ensure_gateway_resources(self) -> None:
        statuses = gateway_resource_statuses_for_settings(self.settings)
        for status in statuses:
            detail = f" ({status.result.detail})" if status.result.detail else ""
            if status.result.status == "failed":
                logger.warning(
                    "Gateway resource ensure failed: %s '%s': %s%s",
                    status.label,
                    status.name,
                    status.result.status,
                    detail,
                )
                continue
            logger.info(
                "Gateway resource ensure: %s '%s': %s%s",
                status.label,
                status.name,
                status.result.status,
                detail,
            )

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the daemon."""
        logger.info("Shutdown requested")
        self._shutdown_requested = True

    def _spawn_dispatch_task(self, coro: asyncio.Future) -> None:
        """Track a fire-and-forget dispatch task so polling stays responsive."""
        if not hasattr(self, "_inflight_dispatch_tasks"):
            self._inflight_dispatch_tasks = set()
        task = asyncio.create_task(coro)
        self._inflight_dispatch_tasks.add(task)

        def _done_callback(done_task: asyncio.Task) -> None:
            self._inflight_dispatch_tasks.discard(done_task)
            with contextlib.suppress(BaseException):
                done_task.result()

        task.add_done_callback(_done_callback)

    async def _flush_inflight_on_shutdown(self, timeout: float = 1.0) -> None:
        if not getattr(self, "_shutdown_requested", False):
            return
        tasks = getattr(self, "_inflight_dispatch_tasks", set())
        if not tasks:
            return
        await asyncio.wait(tasks, timeout=timeout)

    def shutdown(self) -> None:
        """Perform cleanup on shutdown."""
        logger.info("Shutting down...")
        try:
            self.connector.shutdown()
        except Exception as exc:
            logger.warning("Error shutting down connector: %s", exc)
        try:
            self.store.close()
        except Exception as exc:
            logger.warning("Error closing store: %s", exc)
        memory_service = getattr(self, "memory_service", None)
        if memory_service is not None:
            try:
                memory_service.close()
            except Exception as exc:
                logger.warning("Error closing memory service: %s", exc)
        logger.info("Shutdown complete")

    async def run_forever(self) -> None:
        tasks = [asyncio.create_task(self._poll_imessage_loop()), asyncio.create_task(self._run_executor_loop())]
        if self.mail_ingress is not None:
            tasks.append(asyncio.create_task(self._poll_mail_loop()))
        if self.reminders_ingress is not None:
            tasks.append(asyncio.create_task(self._poll_reminders_loop()))
        if self.notes_ingress is not None:
            tasks.append(asyncio.create_task(self._poll_notes_loop()))
        if self.calendar_ingress is not None:
            tasks.append(asyncio.create_task(self._poll_calendar_loop()))
        if self.companion is not None:
            tasks.append(asyncio.create_task(self._companion_loop()))
        if self.ambient is not None:
            tasks.append(asyncio.create_task(self._ambient_loop()))
        if getattr(self, "memory_service", None) is not None:
            tasks.append(asyncio.create_task(self._memory_maintenance_loop()))
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            return
        if self._inflight_dispatch_tasks:
            done, pending = await asyncio.wait(self._inflight_dispatch_tasks, timeout=5.0)
            if pending:
                logger.warning("Shutdown with %d in-flight dispatch tasks still pending", len(pending))

    async def _run_executor_loop(self) -> None:
        """Background worker loop for durable run jobs."""
        try:
            await self.run_executor.run_forever(lambda: self._shutdown_requested)
        except asyncio.CancelledError:
            logger.info("Run executor loop cancelled during shutdown")
            return
        except Exception as exc:
            logger.exception("Run executor loop error: %s", exc)

    async def _companion_loop(self) -> None:
        """Companion proactive observation loop."""
        assert self.companion is not None
        logger.info("Companion loop started")
        try:
            await self.companion.run_forever(lambda: self._shutdown_requested)
        except Exception as exc:
            logger.exception("Companion loop error: %s", exc)

    async def _ambient_loop(self) -> None:
        """Ambient scanner loop — passive context enrichment."""
        assert self.ambient is not None
        logger.info("Ambient scanner loop started")
        try:
            await self.ambient.run_forever(lambda: self._shutdown_requested)
        except Exception as exc:
            logger.exception("Ambient scanner loop error: %s", exc)

    async def _memory_maintenance_loop(self) -> None:
        """Memory maintenance loop for v2 canonical store."""
        assert self.memory_service is not None
        logger.info("Memory maintenance loop started")
        while not self._shutdown_requested:
            try:
                # Keep canonical memory aligned with legacy files during rollout.
                self.memory_service.backfill_from_legacy()
                stats = self.memory_service.run_maintenance()
                if stats["expired_deleted"] or stats["cap_deleted"]:
                    logger.info(
                        "Memory maintenance pruned expired=%s cap=%s",
                        stats["expired_deleted"],
                        stats["cap_deleted"],
                    )
            except Exception as exc:
                logger.exception("Memory maintenance loop error: %s", exc)
            await asyncio.sleep(self.settings.memory_v2_maintenance_interval_seconds)

    async def _poll_imessage_loop(self) -> None:
        """iMessage polling loop (original behaviour)."""
        while not self._shutdown_requested:
            try:
                sender_allowlist = self.settings.allowed_senders if self.settings.only_poll_allowed_senders else None
                if self.settings.only_poll_allowed_senders and not (sender_allowlist or []):
                    logger.warning(
                        "only_poll_allowed_senders=true but allowed_senders is empty; polling disabled until configured."
                    )
                    await asyncio.sleep(self.settings.poll_interval_seconds)
                    continue
                if not self.settings.messages_db_path.exists():
                    self._throttled_messages_db_warning(
                        f"Messages DB not found at {self.settings.messages_db_path}. "
                        "Update apple_flow_messages_db_path in .env and ensure Messages is enabled on this Mac."
                    )
                    await asyncio.sleep(self.settings.poll_interval_seconds)
                    continue
                messages = self.ingress.fetch_new(
                    since_rowid=self._last_rowid,
                    sender_allowlist=sender_allowlist,
                    require_sender_filter=self.settings.only_poll_allowed_senders,
                )

                # Update in-memory cursor for all fetched messages; write to DB once after batch
                dispatchable = []
                for msg in messages:
                    if self._shutdown_requested:
                        break
                    self._last_rowid = max(int(msg.id), self._last_rowid or 0)
                    if msg.is_from_me:
                        continue
                    if not msg.text.strip():
                        logger.info("Ignoring empty inbound rowid=%s sender=%s", msg.id, msg.sender)
                        continue
                    if self._consume_restart_echo_suppress(msg.sender, msg.text):
                        logger.info("Ignoring restart confirmation echo from %s (rowid=%s)", msg.sender, msg.id)
                        continue
                    logger.info(
                        "Inbound message rowid=%s sender=%s chars=%s text=%r",
                        msg.id,
                        msg.sender,
                        len(msg.text),
                        msg.text[:120],
                    )
                    if self.egress.was_recent_outbound(msg.sender, msg.text):
                        logger.info("Ignoring probable outbound echo from %s (rowid=%s)", msg.sender, msg.id)
                        continue
                    # Startup catch-up window: skip messages older than N seconds at boot
                    if self.settings.startup_catchup_window_seconds > 0:
                        try:
                            msg_time = datetime.fromisoformat(msg.received_at).replace(tzinfo=UTC)
                        except Exception:
                            msg_time = None
                        if msg_time is not None:
                            cutoff = self._startup_time - timedelta(
                                seconds=self.settings.startup_catchup_window_seconds
                            )
                            if msg_time < cutoff:
                                logger.info(
                                    "Skipping stale message rowid=%s (received %s, older than startup window of %ds)",
                                    msg.id,
                                    msg.received_at,
                                    self.settings.startup_catchup_window_seconds,
                                )
                                continue
                    if not self.policy.is_sender_allowed(msg.sender):
                        logger.info("Blocked message from non-allowlisted sender: %s", msg.sender)
                        if self.settings.notify_blocked_senders:
                            self.egress.send(msg.sender, "Apple Flow: sender not authorized for this relay.")
                        continue
                    if not self.policy.is_under_rate_limit(msg.sender, datetime.now(UTC)):
                        logger.info("Rate limit triggered for sender: %s", msg.sender)
                        if self.settings.notify_rate_limited_senders:
                            self.egress.send(msg.sender, "Apple Flow: rate limit exceeded, please retry in a minute.")
                        continue
                    dispatchable.append(msg)

                # Persist the updated cursor once after scanning the batch
                if messages:
                    try:
                        self.store.set_state("last_rowid", str(self._last_rowid))
                    except sqlite3.OperationalError as exc:
                        self._throttled_state_db_warning(
                            f"State DB write failed ({exc}). Check apple_flow_db_path and filesystem permissions."
                        )

                async def _dispatch_imessage(msg):
                    parsed = parse_command((msg.text or "").strip())
                    use_fastlane = parsed.kind in _FASTLANE_COMMANDS

                    async def _run_dispatch() -> None:
                        try:
                            started_at = time.monotonic()
                            result = await asyncio.to_thread(self.orchestrator.handle_message, msg)
                            duration = time.monotonic() - started_at
                            if result.response in {"ignored_empty", "ignored_missing_chat_prefix"}:
                                logger.info(
                                    "Ignored rowid=%s sender=%s reason=%s",
                                    msg.id,
                                    msg.sender,
                                    result.response,
                                )
                                return
                            logger.info(
                                "Handled rowid=%s sender=%s kind=%s run_id=%s duration=%.2fs",
                                msg.id,
                                msg.sender,
                                result.kind.value,
                                result.run_id,
                                duration,
                            )
                        except Exception as exc:
                            logger.exception(
                                "Unhandled iMessage dispatch failure rowid=%s sender=%s: %s",
                                msg.id,
                                msg.sender,
                                exc,
                            )
                            try:
                                self.egress.send(
                                    msg.sender,
                                    "⚠️ I hit an internal error while handling that request. "
                                    "Please send `status` and retry if needed.",
                                )
                            except Exception:
                                logger.exception(
                                    "Failed to send fallback iMessage error rowid=%s sender=%s",
                                    msg.id,
                                    msg.sender,
                                )

                    if use_fastlane:
                        await _run_dispatch()
                        return
                    async with self._concurrency_sem:
                        await _run_dispatch()

                if dispatchable:
                    for msg in dispatchable:
                        self._spawn_dispatch_task(_dispatch_imessage(msg))
                    await self._flush_inflight_on_shutdown()
            except sqlite3.OperationalError as exc:
                if "unable to open database file" in str(exc).lower():
                    self._throttled_messages_db_warning(
                        f"Messages DB open failed ({exc}). Grant Terminal Full Disk Access and verify "
                        f"apple_flow_messages_db_path={self.settings.messages_db_path} "
                        f"(exists={self.settings.messages_db_path.exists()})"
                    )
                else:
                    logger.exception("Relay sqlite operational error: %s", exc)
            except Exception as exc:  # pragma: no cover - runtime safety
                logger.exception("Relay loop error: %s", exc)

            await asyncio.sleep(self.settings.poll_interval_seconds)
        await self._flush_inflight_on_shutdown(timeout=2.0)

    def _consume_restart_echo_suppress(self, sender: str, text: str) -> bool:
        """Consume one short-lived restart echo suppress marker, if present and matching."""
        raw_marker = self.store.get_state("system_restart_echo_suppress")
        if not raw_marker:
            return False
        try:
            marker = json.loads(raw_marker)
            expires_at = float(marker.get("expires_at", 0.0))
            if time.time() > expires_at:
                self.store.set_state("system_restart_echo_suppress", "")
                return False
            marker_sender = str(marker.get("sender", ""))
            marker_text = str(marker.get("text", ""))
            if marker_sender == sender and _normalize_echo_text(marker_text) == _normalize_echo_text(text):
                self.store.set_state("system_restart_echo_suppress", "")
                return True
        except Exception:
            # Clear malformed marker to avoid repeated parse failures.
            self.store.set_state("system_restart_echo_suppress", "")
            return False
        return False

    async def _poll_mail_loop(self) -> None:
        """Apple Mail polling loop — runs alongside iMessage when enabled."""
        assert self.mail_ingress is not None
        assert self.mail_egress is not None
        assert self.mail_orchestrator is not None
        if not hasattr(self, "_inflight_mail_ids"):
            self._inflight_mail_ids = set()

        logger.info("Apple Mail polling loop started")
        while not self._shutdown_requested:
            try:
                mail_allowlist = self.settings.mail_allowed_senders or None
                messages = self.mail_ingress.fetch_new(
                    sender_allowlist=mail_allowlist,
                    require_sender_filter=bool(mail_allowlist),
                )
                dispatchable_mail = []
                suppressed_empty = 0
                suppressed_echo = 0
                suppressed_inflight = 0
                for msg in messages:
                    if self._shutdown_requested:
                        break
                    if not msg.text.strip():
                        suppressed_empty += 1
                        continue
                    logger.debug(
                        "Inbound email id=%s sender=%s chars=%s text=%r",
                        msg.id,
                        msg.sender,
                        len(msg.text),
                        msg.text[:120],
                    )
                    if self.mail_egress.was_recent_outbound(msg.sender, msg.text):
                        suppressed_echo += 1
                        logger.debug("Ignoring probable outbound echo from %s (id=%s)", msg.sender, msg.id)
                        continue
                    if msg.id in self._inflight_mail_ids:
                        suppressed_inflight += 1
                        logger.debug("Skipping in-flight inbound email id=%s sender=%s", msg.id, msg.sender)
                        continue
                    dispatchable_mail.append(msg)
                    self._inflight_mail_ids.add(msg.id)

                async def _dispatch_mail(msg):
                    async with self._concurrency_sem:
                        try:
                            started_at = time.monotonic()
                            result = await asyncio.to_thread(self.mail_orchestrator.handle_message, msg)
                            duration = time.monotonic() - started_at
                            if result.response in {"ignored_empty", "ignored_missing_chat_prefix", "duplicate"}:
                                if result.response == "duplicate":
                                    logger.debug(
                                        "Ignoring duplicate inbound email id=%s sender=%s",
                                        msg.id,
                                        msg.sender,
                                    )
                                else:
                                    logger.info(
                                        "Ignored email id=%s sender=%s reason=%s",
                                        msg.id,
                                        msg.sender,
                                        result.response,
                                    )
                                return
                            logger.info(
                                "Handled email id=%s sender=%s kind=%s run_id=%s duration=%.2fs",
                                msg.id,
                                msg.sender,
                                result.kind.value,
                                result.run_id,
                                duration,
                            )
                            # Forward actionable mail responses to owner via iMessage.
                            if self._mail_owner and result.response:
                                logger.info(
                                    "Forwarding mail response to owner sender=%s kind=%s chars=%s",
                                    msg.sender,
                                    result.kind.value,
                                    len(result.response),
                                )
                                preview = result.response[:200]
                                if result.kind.value in ("task", "project"):
                                    imsg = f"📧 Mail from {msg.sender} needs approval.\n\n{preview}"
                                else:
                                    imsg = f"📧 Mail from {msg.sender}\n\n{preview}"
                                self.egress.send(self._mail_owner, imsg)
                        except Exception as exc:
                            logger.exception(
                                "Unhandled mail dispatch failure id=%s sender=%s: %s",
                                msg.id,
                                msg.sender,
                                exc,
                            )
                        finally:
                            self._inflight_mail_ids.discard(msg.id)

                if dispatchable_mail:
                    logger.info(
                        "Mail poll fetched=%s dispatchable=%s skipped_empty=%s skipped_echo=%s skipped_inflight=%s",
                        len(messages),
                        len(dispatchable_mail),
                        suppressed_empty,
                        suppressed_echo,
                        suppressed_inflight,
                    )
                    for msg in dispatchable_mail:
                        self._spawn_dispatch_task(_dispatch_mail(msg))
                    await self._flush_inflight_on_shutdown()
                elif messages:
                    logger.info(
                        "Mail poll fetched=%s dispatchable=0 skipped_empty=%s skipped_echo=%s skipped_inflight=%s",
                        len(messages),
                        suppressed_empty,
                        suppressed_echo,
                        suppressed_inflight,
                    )
            except Exception as exc:
                logger.exception("Mail polling loop error: %s", exc)

            await asyncio.sleep(self.settings.poll_interval_seconds)
        await self._flush_inflight_on_shutdown(timeout=2.0)

    async def _poll_reminders_loop(self) -> None:
        """Apple Reminders polling loop — runs alongside iMessage/Mail when enabled."""
        assert self.reminders_ingress is not None
        assert self.reminders_egress is not None
        assert self.reminders_orchestrator is not None

        logger.info("Apple Reminders polling loop started (list=%r)", self.settings.reminders_list_name)
        while not self._shutdown_requested:
            try:
                messages = self.reminders_ingress.fetch_new()
                dispatchable_reminders = []
                for msg in messages:
                    if self._shutdown_requested:
                        break
                    if not msg.text.strip():
                        logger.info("Ignoring empty reminder id=%s", msg.id)
                        continue

                    reminder_id = msg.context.get("reminder_id", "")
                    occurrence_key = msg.context.get("occurrence_key", "") or f"{reminder_id}|"
                    reminder_name = msg.context.get("reminder_name", "")
                    logger.info(
                        "Inbound reminder id=%s name=%r sender=%s chars=%s",
                        msg.id,
                        reminder_name,
                        msg.sender,
                        len(msg.text),
                    )

                    self.reminders_ingress.mark_processed_occurrence(occurrence_key)
                    dispatchable_reminders.append(msg)

                async def _dispatch_reminder(msg):
                    async with self._concurrency_sem:
                        try:
                            started_at = time.monotonic()
                            result = await asyncio.to_thread(self.reminders_orchestrator.handle_message, msg)
                            duration = time.monotonic() - started_at
                            reminder_id = msg.context.get("reminder_id", "")
                            logger.info(
                                "Handled reminder id=%s kind=%s run_id=%s duration=%.2fs",
                                msg.id,
                                result.kind.value,
                                result.run_id,
                                duration,
                            )
                            if result.response and reminder_id:
                                if result.kind.value in ("task", "project"):
                                    self.reminders_egress.annotate_reminder(
                                        reminder_id,
                                        f"[Apple Flow] Awaiting approval — check iMessage.\n\n{result.response[:500]}",
                                    )
                                else:
                                    list_name = msg.context.get("list_name", self.settings.reminders_list_name)
                                    self.reminders_egress.move_to_archive(
                                        reminder_id=reminder_id,
                                        result_text=f"[Apple Flow Result]\n\n{result.response}",
                                        source_list_name=list_name,
                                        archive_list_name=self.settings.reminders_archive_list_name,
                                    )
                        except Exception as exc:
                            logger.exception(
                                "Unhandled reminders dispatch failure id=%s sender=%s: %s",
                                msg.id,
                                msg.sender,
                                exc,
                            )

                if dispatchable_reminders:
                    for msg in dispatchable_reminders:
                        self._spawn_dispatch_task(_dispatch_reminder(msg))
                    await self._flush_inflight_on_shutdown()
            except Exception as exc:
                logger.exception("Reminders polling loop error: %s", exc)

            await asyncio.sleep(self.settings.reminders_poll_interval_seconds)

    async def _poll_notes_loop(self) -> None:
        """Apple Notes polling loop."""
        assert self.notes_ingress is not None
        assert self.notes_egress is not None
        assert self.notes_orchestrator is not None

        logger.info("Apple Notes polling loop started (folder=%r)", self.settings.notes_folder_name)
        while not self._shutdown_requested:
            try:
                messages = await asyncio.to_thread(self.notes_ingress.fetch_new)
                dispatchable_notes = []
                for msg in messages:
                    if self._shutdown_requested:
                        break
                    if not msg.text.strip():
                        continue

                    note_title = msg.context.get("note_title", "")
                    logger.info("Inbound note id=%s title=%r chars=%s", msg.id, note_title, len(msg.text))
                    dispatchable_notes.append(msg)

                async def _dispatch_note(msg):
                    async with self._concurrency_sem:
                        try:
                            started_at = time.monotonic()
                            result = await asyncio.to_thread(self.notes_orchestrator.handle_message, msg)
                            duration = time.monotonic() - started_at
                            note_id = msg.context.get("note_id", "")
                            logger.info("Handled note id=%s kind=%s duration=%.2fs", msg.id, result.kind.value, duration)
                            if result.response and note_id:
                                folder_name = msg.context.get("folder_name", self.settings.notes_folder_name)
                                if result.kind.value in ("task", "project"):
                                    self.notes_egress.append_result(
                                        note_id,
                                        "[Apple Flow] Awaiting approval — check iMessage to approve/deny.",
                                    )
                                else:
                                    self.notes_egress.move_to_archive(
                                        note_id=note_id,
                                        result_text=f"\n\n[Apple Flow Result]\n{result.response}",
                                        source_folder_name=folder_name,
                                        archive_subfolder_name=self.settings.notes_archive_folder_name,
                                    )
                            # Mark processed only after the run path completes so failed runs can be retried.
                            if note_id:
                                self.notes_ingress.mark_processed(note_id)
                        except Exception as exc:
                            logger.exception(
                                "Unhandled notes dispatch failure id=%s sender=%s: %s",
                                msg.id,
                                msg.sender,
                                exc,
                            )

                if dispatchable_notes:
                    for msg in dispatchable_notes:
                        self._spawn_dispatch_task(_dispatch_note(msg))
                    await self._flush_inflight_on_shutdown()
            except Exception as exc:
                logger.exception("Notes polling loop error: %s", exc)

            await asyncio.sleep(self.settings.notes_poll_interval_seconds)

    async def _poll_calendar_loop(self) -> None:
        """Apple Calendar polling loop."""
        assert self.calendar_ingress is not None
        assert self.calendar_egress is not None
        assert self.calendar_orchestrator is not None

        logger.info("Apple Calendar polling loop started (calendar=%r)", self.settings.calendar_name)
        while not self._shutdown_requested:
            try:
                messages = self.calendar_ingress.fetch_new()
                dispatchable_calendar = []
                for msg in messages:
                    if self._shutdown_requested:
                        break
                    if not msg.text.strip():
                        continue

                    event_id = msg.context.get("event_id", "")
                    event_summary = msg.context.get("event_summary", "")
                    logger.info("Inbound calendar event id=%s summary=%r chars=%s", msg.id, event_summary, len(msg.text))

                    self.calendar_ingress.mark_processed(event_id)
                    dispatchable_calendar.append(msg)

                async def _dispatch_calendar(msg):
                    async with self._concurrency_sem:
                        try:
                            started_at = time.monotonic()
                            result = await asyncio.to_thread(self.calendar_orchestrator.handle_message, msg)
                            duration = time.monotonic() - started_at
                            event_id = msg.context.get("event_id", "")
                            logger.info("Handled calendar event id=%s kind=%s duration=%.2fs", msg.id, result.kind.value, duration)
                            if result.response and event_id:
                                if result.kind.value in ("task", "project"):
                                    self.calendar_egress.annotate_event(
                                        event_id,
                                        "[Apple Flow] Awaiting approval — check iMessage to approve/deny.",
                                    )
                                else:
                                    self.calendar_egress.annotate_event(event_id, result.response)
                        except Exception as exc:
                            logger.exception(
                                "Unhandled calendar dispatch failure id=%s sender=%s: %s",
                                msg.id,
                                msg.sender,
                                exc,
                            )

                if dispatchable_calendar:
                    for msg in dispatchable_calendar:
                        self._spawn_dispatch_task(_dispatch_calendar(msg))
                    await self._flush_inflight_on_shutdown()
            except Exception as exc:
                logger.exception("Calendar polling loop error: %s", exc)

            await asyncio.sleep(self.settings.calendar_poll_interval_seconds)

    def send_startup_intro(self) -> None:
        if not self.settings.allowed_senders:
            logger.info("Startup intro skipped: no allowed_senders configured.")
            return
        recipient = self.settings.allowed_senders[0]

        connector_type = self.settings.get_connector_type()
        if connector_type == "claude-cli":
            model_val = self.settings.claude_cli_model or "claude default"
            connector_line = "⚙️  Engine: claude -p (stateless)"
        elif connector_type == "gemini-cli":
            model_val = self.settings.gemini_cli_model or "gemini default"
            connector_line = "⚙️  Engine: gemini -p (stateless)"
        elif connector_type == "cline":
            model_val = self.settings.cline_model or "cline default"
            connector_line = "⚙️  Engine: cline -y (agentic)"
        else:
            model_val = self.settings.codex_cli_model or "codex default"
            connector_line = "⚙️  Engine: codex exec (stateless)"
        model_line = f"🧠 Model: {model_val}"

        if self.settings.require_chat_prefix:
            chat_line = f"💬 {self.settings.chat_prefix} <msg>      chat"
            mode_hint = f"Prefix mode: start messages with {self.settings.chat_prefix}"
        else:
            chat_line = "💬 Just type naturally — ask anything!"
            mode_hint = "Natural mode: no prefix needed"

        commands = [
            chat_line,
            "",
            f"ℹ️  {mode_hint}",
            "❓ help",
            "✅ approve <id>  |  ❌ deny <id>  |  ❌❌ deny all  |  📊 status",
            "🏥 health  |  🔍 history: [query]  |  📈 usage  |  📋 logs  |  🔄 clear context",
            "🔧 system: stop  |  restart  |  kill provider  |  cancel run <run_id>",
            "",
            "Power users:",
            "⚡ task: <cmd>        execute  (needs ✅)",
            "🚀 project: <spec>    multi-step (needs ✅)",
            f"💬 {self.settings.chat_prefix} <msg>  |  💡 idea:  |  📋 plan:",
        ]
        gateways = ["💬 iMessage   → always active"]
        if self.settings.enable_mail_polling:
            gateways.append("📧 Mail       → inbox polling active")
        if self.settings.enable_reminders_polling:
            gateways.append(f"🔔 Reminders  → list: {self.settings.reminders_list_name}")
        if self.settings.enable_notes_polling:
            gateways.append(f"📝 Notes      → folder: {self.settings.notes_folder_name}")
        if self.settings.enable_calendar_polling:
            gateways.append(f"📅 Calendar   → calendar: {self.settings.calendar_name}")
        if self.companion is not None:
            gateways.append("🤖 Companion  → proactive observations active")

        gateway_section = ""
        if gateways:
            gateway_section = (
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🌐 GATEWAYS\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                + "\n".join(gateways) + "\n"
            )

        intro = (
            "🤖✨ APPLE FLOW ONLINE ✨🤖\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{connector_line}\n"
            f"{model_line}\n"
            f"📂 Workspace: {self.settings.default_workspace}\n"
            f"🔐 Auth: {'allowed senders only' if self.settings.only_poll_allowed_senders else 'open'}\n"
            f"⏱️  Timeout: {int(self.settings.codex_turn_timeout_seconds)}s\n"
            + gateway_section
            + "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ COMMANDS\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(commands)
        )
        try:
            self.egress.send(recipient, intro)
            logger.info("Startup intro sent to %s", recipient)
        except Exception as exc:  # pragma: no cover - runtime safety
            logger.warning("Failed to send startup intro: %s", exc)

    def _throttled_messages_db_warning(self, message: str, interval_seconds: float = 30.0) -> None:
        now = time.time()
        if (now - self._last_messages_db_error_at) >= interval_seconds:
            logger.warning(message)
            self._last_messages_db_error_at = now

    def _throttled_state_db_warning(self, message: str, interval_seconds: float = 30.0) -> None:
        now = time.time()
        if (now - self._last_state_db_error_at) >= interval_seconds:
            logger.warning(message)
            self._last_state_db_error_at = now


async def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = RelaySettings()
    migrate_legacy_db_if_needed(settings)
    daemon = RelayDaemon(settings)

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def handle_signal(sig: signal.Signals) -> None:
        logger.info("Received signal %s", sig.name)
        daemon.request_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal, sig)

    channels = ["iMessages"]
    if settings.enable_mail_polling:
        channels.append("Apple Mail")
    if settings.enable_reminders_polling:
        channels.append("Apple Reminders")
    if settings.enable_notes_polling:
        channels.append("Apple Notes")
    if settings.enable_calendar_polling:
        channels.append("Apple Calendar")
    if settings.enable_companion:
        channels.append("Companion")

    logger.info(
        "Apple Flow running (foreground). Allowed senders=%s, strict_sender_poll=%s, channels=%s",
        len(settings.allowed_senders),
        settings.only_poll_allowed_senders,
        " + ".join(channels),
    )
    if settings.send_startup_intro:
        daemon.send_startup_intro()
    logger.info("Ready. Waiting for inbound %s. Press Ctrl+C to stop.", " + ".join(channels))

    try:
        await daemon.run_forever()
    except asyncio.CancelledError:
        logger.info("Daemon run loop cancelled during shutdown")
    finally:
        daemon.shutdown()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run())
