from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import logging
import shutil
import signal
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .ambient import AmbientScanner
from .attachments import AttachmentProcessor
from .calendar_egress import AppleCalendarEgress
from .calendar_ingress import AppleCalendarIngress
from .claude_cli_connector import ClaudeCliConnector
from .cline_connector import ClineConnector
from .codex_cli_connector import CodexCliConnector
from .commanding import CommandKind, parse_command
from .companion import CompanionLoop
from .config import RelaySettings
from .csv_audit import CsvAuditLogger
from .egress import IMessageEgress
from .gateway_health import gateway_health_payload, gateway_health_state_key, now_utc_iso
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
from .ollama_connector import OllamaConnector
from .orchestrator import RelayOrchestrator
from .policy import PolicyEngine
from .process_registry import ManagedProcessRegistry
from .protocols import ConnectorProtocol
from .reminders_egress import AppleRemindersEgress
from .reminders_ingress import AppleRemindersIngress
from .run_executor import RunExecutor
from .scheduler import FollowUpScheduler
from .runtime_health import (
    daemon_loop_health_payload,
    daemon_loop_health_state_key,
    daemon_watchdog_payload,
    daemon_watchdog_state_key,
)
from . import reminders_runtime_gate
from .store import SQLiteStore
from .models import RunState
from .utils import normalize_echo_text, normalize_sender

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

_ATTACHMENT_PLACEHOLDER_TEXTS = {"\uFFFC", "￼"}

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
        csv_audit_logger = None
        if settings.enable_csv_audit_log:
            csv_path = Path(settings.csv_audit_log_path)
            if not csv_path.is_absolute():
                csv_path = Path(__file__).resolve().parents[2] / settings.csv_audit_log_path
            csv_audit_logger = CsvAuditLogger(
                path=csv_path,
                include_headers_if_missing=settings.csv_audit_include_headers_if_missing,
            )
        self.store = SQLiteStore(Path(settings.db_path), csv_audit_logger=csv_audit_logger)
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
        self.attachment_processor = AttachmentProcessor(
            max_attachment_size_mb=settings.max_attachment_size_mb,
            max_files_per_message=settings.attachment_max_files_per_message,
            max_text_chars_per_file=settings.attachment_max_text_chars_per_file,
            max_total_text_chars=settings.attachment_max_total_text_chars,
            enable_image_ocr=settings.attachment_enable_image_ocr,
            enable_audio_transcription=settings.attachment_enable_audio_transcription,
            audio_transcription_command=settings.attachment_audio_transcription_command,
            audio_transcription_model=settings.attachment_audio_transcription_model,
            audio_transcription_language=settings.attachment_audio_transcription_language,
            audio_transcription_temp_dir=settings.attachment_temp_dir,
        )

        # Choose connector based on configuration
        connector_type = settings.get_connector_type()
        known_connectors = {
            "codex-cli",
            "claude-cli",
            "gemini-cli",
            "kilo-cli",
            "cline",
            "ollama",
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
        elif connector_type == "ollama":
            logger.info("Using native Ollama connector (/api/chat) for local execution")
            self.connector = OllamaConnector(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                workspace=settings.default_workspace,
                timeout=settings.codex_turn_timeout_seconds,
                context_window=settings.ollama_context_window,
                inject_tools_context=settings.inject_tools_context,
                system_prompt=settings.personality_prompt.replace(
                    "{workspace}", settings.default_workspace
                ),
                num_ctx=settings.ollama_num_ctx,
                temperature=settings.ollama_temperature,
                auto_pull_model=settings.ollama_auto_pull_model,
                enable_thinking=settings.ollama_enable_thinking,
                tool_timeout_seconds=settings.ollama_tool_timeout_seconds,
                max_tool_iterations=settings.ollama_max_tool_iterations,
                max_tool_output_chars=settings.ollama_max_tool_output_chars,
                allowed_workspaces=settings.allowed_workspaces,
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
        soul_path = Path(settings.soul_file) if settings.soul_file.strip() else None
        if soul_path and not soul_path.is_absolute():
            soul_path = Path(__file__).resolve().parents[2] / settings.soul_file
        if soul_path and soul_path.is_file():
            try:
                self._soul_prompt = soul_path.read_text(encoding="utf-8").strip()
                logger.info("Loaded SOUL.md from %s (%d chars)", soul_path, len(self._soul_prompt))
            except Exception as exc:
                logger.warning("Failed to read SOUL.md at %s: %s", soul_path, exc)
        elif soul_path:
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

        # Canonical memory v2
        self.memory_service: MemoryService | None = None
        if settings.enable_memory and self._office_path and settings.enable_memory_v2:
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
                max_storage_mb=settings.memory_max_storage_mb,
                include_legacy_fallback=settings.memory_v2_include_legacy_fallback,
                default_scope=settings.memory_v2_scope,
            )
            if settings.memory_v2_migrate_on_start:
                self.memory_service.backfill_from_legacy()
            logger.info(
                "Canonical memory v2 initialized (enabled=%s, db=%s)",
                settings.enable_memory_v2,
                db_path,
            )

        # Follow-up scheduler (SQLite-backed)
        self.scheduler: FollowUpScheduler | None = None
        if settings.enable_follow_ups:
            self.scheduler = FollowUpScheduler(self.store)
            logger.info("Follow-up scheduler enabled")

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
        file_aliases = settings.get_file_aliases()
        orchestrator_kwargs = dict(
            connector=self.connector,
            store=self.store,
            allowed_workspaces=settings.allowed_workspaces,
            default_workspace=settings.default_workspace,
            approval_ttl_minutes=settings.approval_ttl_minutes,
            chat_prefix=settings.chat_prefix,
            workspace_aliases=workspace_aliases,
            file_aliases=file_aliases,
            auto_context_messages=settings.auto_context_messages,
            enable_progress_streaming=settings.enable_progress_streaming,
            progress_update_interval_seconds=settings.progress_update_interval_seconds,
            execution_heartbeat_seconds=settings.execution_heartbeat_seconds,
            checkpoint_on_timeout=settings.checkpoint_on_timeout,
            auto_resume_on_timeout=settings.auto_resume_on_timeout,
            max_resume_attempts=settings.max_resume_attempts,
            enable_verifier=settings.enable_verifier,
            enable_attachments=settings.enable_attachments,
            attachment_processor=self.attachment_processor,
            personality_prompt=settings.personality_prompt,
            shutdown_callback=self.request_shutdown,
            helper_recycle_callback=self.recycle_helpers,
            log_notes_egress=notes_log_egress_obj,
            notes_log_folder_name=settings.notes_log_folder_name,
            memory=self.memory,
            memory_service=self.memory_service,
            scheduler=self.scheduler,
            run_executor=None,
            log_file_path=settings.log_file_path,
            phone_owner_number=settings.phone_owner_number or (settings.allowed_senders[0] if settings.allowed_senders else ""),
            phone_tts_voice=settings.phone_tts_voice,
            phone_tts_rate=settings.phone_tts_rate,
            phone_tts_engine=settings.phone_tts_engine,
            phone_piper_command=settings.phone_piper_command,
            phone_piper_model_path=settings.phone_piper_model_path,
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
        self._inflight_dispatch_started_at: dict[asyncio.Task, float] = {}
        self._inflight_mail_ids: set[str] = set()

        persisted_cursor = self.store.get_state("last_rowid")
        self._last_rowid: int | None = int(persisted_cursor) if persisted_cursor is not None else None
        self._last_messages_db_error_at: float = 0.0
        self._last_state_db_error_at: float = 0.0
        self._shutdown_requested = False
        self._last_busy_at = time.monotonic()
        self._event_loop_lag_seconds = 0.0
        self._event_loop_lag_failures = 0
        self._last_connector_completion_at = ""
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
            gateway = self._gateway_name_from_label(status.label)
            if status.result.status == "failed":
                if gateway and hasattr(self, "store"):
                    self._record_gateway_failure(gateway, status.result.detail or status.result.status)
                logger.warning(
                    "Gateway resource ensure failed: %s '%s': %s%s",
                    status.label,
                    status.name,
                    status.result.status,
                    detail,
                )
                continue
            if gateway and hasattr(self, "store"):
                self._record_gateway_success(gateway)
            logger.info(
                "Gateway resource ensure: %s '%s': %s%s",
                status.label,
                status.name,
                status.result.status,
                detail,
            )

    @staticmethod
    def _gateway_name_from_label(label: str) -> str:
        lowered = label.lower()
        if "mail" in lowered:
            return "mail"
        if "reminders" in lowered:
            return "reminders"
        if "notes" in lowered:
            return "notes"
        if "calendar" in lowered:
            return "calendar"
        return ""

    def _record_gateway_success(self, gateway: str) -> None:
        if not gateway or not hasattr(self, "store"):
            return
        previous_raw = self.store.get_state(gateway_health_state_key(gateway))
        previous_healthy = True
        previous_reason = ""
        if previous_raw:
            try:
                previous = json.loads(previous_raw)
                previous_healthy = bool(previous.get("healthy", True))
                previous_reason = str(previous.get("last_failure_reason", ""))
            except (TypeError, ValueError):
                previous_healthy = True
        self.store.set_state(
            gateway_health_state_key(gateway),
            gateway_health_payload(
                healthy=True,
                last_success_at=now_utc_iso(),
                last_failure_reason="" if previous_healthy else previous_reason,
            ),
        )
        if not previous_healthy:
            logger.info("Gateway recovered: %s", gateway)

    def _record_gateway_failure(self, gateway: str, reason: str) -> None:
        if not gateway or not hasattr(self, "store"):
            return
        previous_raw = self.store.get_state(gateway_health_state_key(gateway))
        previous_healthy = True
        previous_reason = ""
        if previous_raw:
            try:
                previous = json.loads(previous_raw)
                previous_healthy = bool(previous.get("healthy", True))
                previous_reason = str(previous.get("last_failure_reason", ""))
            except (TypeError, ValueError):
                previous_healthy = True
        self.store.set_state(
            gateway_health_state_key(gateway),
            gateway_health_payload(
                healthy=False,
                last_failure_at=now_utc_iso(),
                last_failure_reason=reason,
            ),
        )
        if previous_healthy or previous_reason != reason:
            logger.warning("Gateway degraded: %s (%s)", gateway, reason)

    @staticmethod
    def _supervisor_backoff_seconds(attempt: int) -> float:
        if attempt <= 1:
            return 1.0
        if attempt == 2:
            return 5.0
        if attempt == 3:
            return 15.0
        return 60.0

    def _read_loop_health_state(self, name: str) -> dict[str, Any]:
        raw = (
            self.store.get_state(daemon_loop_health_state_key(name))
            if hasattr(self, "store") and hasattr(self.store, "get_state")
            else None
        )
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _write_loop_health_state(
        self,
        name: str,
        *,
        healthy: bool,
        last_success_at: str | None = None,
        last_failure_at: str | None = None,
        last_failure_reason: str | None = None,
        restart_count: int | None = None,
        last_restart_at: str | None = None,
    ) -> None:
        if not hasattr(self, "store"):
            return
        previous = self._read_loop_health_state(name)
        self.store.set_state(
            daemon_loop_health_state_key(name),
            daemon_loop_health_payload(
                healthy=healthy,
                last_success_at=last_success_at if last_success_at is not None else str(previous.get("last_success_at", "")),
                last_failure_at=last_failure_at if last_failure_at is not None else str(previous.get("last_failure_at", "")),
                last_failure_reason=(
                    last_failure_reason
                    if last_failure_reason is not None
                    else str(previous.get("last_failure_reason", ""))
                ),
                restart_count=(
                    int(restart_count)
                    if restart_count is not None
                    else int(previous.get("restart_count", 0) or 0)
                ),
                last_restart_at=last_restart_at if last_restart_at is not None else str(previous.get("last_restart_at", "")),
            ),
        )

    def _record_loop_success(self, name: str) -> None:
        self._write_loop_health_state(
            name,
            healthy=True,
            last_success_at=now_utc_iso(),
        )

    def _record_loop_failure(self, name: str, reason: str) -> None:
        self._write_loop_health_state(
            name,
            healthy=False,
            last_failure_at=now_utc_iso(),
            last_failure_reason=reason,
        )

    def _record_loop_restart(self, name: str) -> int:
        previous = self._read_loop_health_state(name)
        restart_count = int(previous.get("restart_count", 0) or 0) + 1
        self._write_loop_health_state(
            name,
            healthy=False,
            restart_count=restart_count,
            last_restart_at=now_utc_iso(),
        )
        return restart_count

    async def _supervise_loop(self, name: str, loop_factory: Any) -> None:
        attempts = 0
        while not self._shutdown_requested:
            try:
                await loop_factory()
                if self._shutdown_requested:
                    return
                attempts += 1
                restarts = self._record_loop_restart(name)
                self._record_loop_failure(name, "unexpected_return")
                logger.warning(
                    "Top-level loop returned unexpectedly: %s (restart_count=%s)",
                    name,
                    restarts,
                )
            except asyncio.CancelledError:
                return
            except Exception as exc:
                attempts += 1
                restarts = self._record_loop_restart(name)
                self._record_loop_failure(name, f"{type(exc).__name__}: {exc}")
                logger.exception(
                    "Top-level loop crashed: %s (restart_count=%s): %s",
                    name,
                    restarts,
                    exc,
                )

            if self._shutdown_requested:
                return
            await asyncio.sleep(self._supervisor_backoff_seconds(attempts))

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the daemon."""
        logger.info("Shutdown requested")
        self._shutdown_requested = True

    def _connector_registry(self) -> Any | None:
        connector = getattr(self, "connector", None)
        if connector is None:
            return None
        registry = getattr(connector, "_processes", None)
        if isinstance(registry, ManagedProcessRegistry):
            return registry
        if registry is not None and hasattr(registry, "active_count") and hasattr(registry, "oldest_age_seconds"):
            return registry
        return None

    def _active_work_counts(self) -> dict[str, int]:
        inflight_dispatch = len(getattr(self, "_inflight_dispatch_tasks", set()))
        active_runs = 0
        if hasattr(self.store, "list_active_runs"):
            try:
                runs = self.store.list_active_runs(limit=200)
            except Exception:
                logger.debug("Failed to list active runs for helper maintenance", exc_info=True)
                runs = []
            active_states = {
                RunState.PLANNING.value,
                RunState.QUEUED.value,
                RunState.RUNNING.value,
                RunState.EXECUTING.value,
                RunState.VERIFYING.value,
            }
            active_runs = sum(1 for run in runs if str(run.get("state", "")) in active_states)
        counts = {
            "active_runs": active_runs,
            "inflight_dispatch": inflight_dispatch,
            "busy": 1 if (active_runs or inflight_dispatch) else 0,
        }
        if counts["busy"]:
            self._last_busy_at = time.monotonic()
        return counts

    def _oldest_inflight_dispatch_seconds(self) -> float:
        started_at = getattr(self, "_inflight_dispatch_started_at", {})
        if not started_at:
            return 0.0
        now = time.monotonic()
        return max(0.0, max(now - ts for ts in started_at.values()))

    def _enabled_watchdog_poll_loops(self) -> list[str]:
        loops = ["imessage"]
        if getattr(self, "mail_ingress", None) is not None:
            loops.append("mail")
        if getattr(self, "reminders_ingress", None) is not None:
            loops.append("reminders")
        if getattr(self, "notes_ingress", None) is not None:
            loops.append("notes")
        if getattr(self, "calendar_ingress", None) is not None:
            loops.append("calendar")
        return loops

    def _poll_loops_stalled(self) -> bool:
        now = datetime.now(UTC)
        threshold = float(getattr(self.settings, "watchdog_poll_stall_seconds", 60.0))
        for name in self._enabled_watchdog_poll_loops():
            state = self._read_loop_health_state(name)
            last_success_at = str(state.get("last_success_at", "") or "")
            if not last_success_at:
                continue
            try:
                success_dt = datetime.fromisoformat(last_success_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if success_dt.tzinfo is None:
                success_dt = success_dt.replace(tzinfo=UTC)
            if (now - success_dt).total_seconds() > threshold:
                return True
        return False

    def _publish_watchdog_state(self) -> None:
        if not hasattr(self, "store"):
            return
        registry = self._connector_registry()
        active_helpers = registry.active_count() if registry is not None else 0
        oldest_helper_age = registry.oldest_age_seconds() if registry is not None else 0.0
        oldest_inflight = self._oldest_inflight_dispatch_seconds()
        degraded_reasons: list[str] = []
        if self._poll_loops_stalled():
            degraded_reasons.append("poll_stalled")
        if oldest_inflight > float(getattr(self.settings, "watchdog_inflight_stall_seconds", 300.0)):
            degraded_reasons.append("inflight_stalled")
        if self._event_loop_lag_failures >= int(getattr(self.settings, "watchdog_event_loop_lag_failures", 3)):
            degraded_reasons.append("event_loop_lag")
        if (
            active_helpers > 0
            and oldest_helper_age
            and oldest_helper_age > float(getattr(self.settings, "helper_recycle_max_age_seconds", 3600.0))
            and not self._active_work_counts()["busy"]
        ):
            degraded_reasons.append("stale_helpers")
        self.store.set_state("runtime_active_helper_count", str(active_helpers))
        self.store.set_state("runtime_oldest_helper_age_seconds", str(float(oldest_helper_age or 0.0)))
        self.store.set_state("runtime_oldest_inflight_dispatch_seconds", str(float(oldest_inflight)))
        self.store.set_state("runtime_event_loop_lag_seconds", str(float(getattr(self, "_event_loop_lag_seconds", 0.0))))
        self.store.set_state("runtime_busy", "1" if self._active_work_counts()["busy"] else "0")
        self.store.set_state(
            daemon_watchdog_state_key(),
            daemon_watchdog_payload(
                healthy=not degraded_reasons,
                degraded_reasons=degraded_reasons,
                last_connector_completion_at=self._last_connector_completion_at,
                oldest_inflight_dispatch_seconds=oldest_inflight,
                active_helper_count=active_helpers,
                oldest_helper_age_seconds=float(oldest_helper_age or 0.0),
                event_loop_lag_seconds=float(getattr(self, "_event_loop_lag_seconds", 0.0)),
                event_loop_lag_failures=int(getattr(self, "_event_loop_lag_failures", 0)),
            ),
        )

    def recycle_helpers(self, force: bool = False) -> str:
        """Soft-recycle tracked helper subprocesses without restarting the parent daemon."""
        counts = self._active_work_counts()
        now = time.monotonic()
        idle_seconds = max(0.0, now - getattr(self, "_last_busy_at", now))
        registry = self._connector_registry()
        active_helpers = registry.active_count() if registry is not None else 0
        oldest_age = registry.oldest_age_seconds() if registry is not None else None

        if not force and counts["busy"]:
            return (
                "Helper recycle skipped: service is busy "
                f"(active_runs={counts['active_runs']}, inflight_dispatch={counts['inflight_dispatch']})."
            )

        if not force and idle_seconds < float(self.settings.helper_recycle_idle_seconds):
            return (
                "Helper recycle skipped: idle window not reached "
                f"({int(idle_seconds)}s < {int(self.settings.helper_recycle_idle_seconds)}s)."
            )

        if active_helpers <= 0:
            return (
                "Helper recycle check complete: no tracked connector helpers are running."
                if not force
                else "Forced helper recycle complete: no tracked connector helpers were running."
            )

        if (
            not force
            and oldest_age is not None
            and oldest_age < float(self.settings.helper_recycle_max_age_seconds)
        ):
            return (
                "Helper recycle skipped: oldest helper age is below threshold "
                f"({int(oldest_age)}s < {int(self.settings.helper_recycle_max_age_seconds)}s)."
            )

        killed = 0
        if hasattr(self.connector, "cancel_active_processes"):
            try:
                killed = int(self.connector.cancel_active_processes())
            except Exception:
                logger.exception("Helper recycle failed while cancelling tracked connector processes")
                return "Helper recycle failed: connector process cancellation raised an error."

        result = (
            f"Recycled {killed} tracked helper process(es); "
            f"idle={int(idle_seconds)}s, oldest_age={int(oldest_age or 0)}s."
        )
        logger.info("Helper recycle completed: %s", result)
        if hasattr(self.store, "set_state"):
            self.store.set_state("helper_maintenance_last_run_at", datetime.now(UTC).isoformat())
            self.store.set_state("helper_maintenance_last_result", result)
        return result

    def _spawn_dispatch_task(self, coro: asyncio.Future) -> None:
        """Track a fire-and-forget dispatch task so polling stays responsive."""
        if not hasattr(self, "_inflight_dispatch_tasks"):
            self._inflight_dispatch_tasks = set()
        if not hasattr(self, "_inflight_dispatch_started_at"):
            self._inflight_dispatch_started_at = {}
        task = asyncio.create_task(coro)
        self._inflight_dispatch_tasks.add(task)
        self._inflight_dispatch_started_at[task] = time.monotonic()
        self._publish_watchdog_state()

        def _done_callback(done_task: asyncio.Task) -> None:
            self._inflight_dispatch_tasks.discard(done_task)
            self._inflight_dispatch_started_at.pop(done_task, None)
            self._publish_watchdog_state()
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

    @staticmethod
    def _invoke_blocking(func: Any, *args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    async def _call_blocking(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(self._invoke_blocking, func, *args, **kwargs)

    async def _send_via_egress(
        self,
        recipient: str,
        text: str,
        *,
        context: dict[str, Any] | None = None,
        egress: Any | None = None,
    ) -> None:
        target = egress or self.egress
        try:
            await self._call_blocking(target.send, recipient, text, context=context)
        except TypeError:
            await self._call_blocking(target.send, recipient, text)

    def _record_connector_completion(self) -> None:
        self._last_connector_completion_at = now_utc_iso()
        if hasattr(self, "store"):
            self.store.set_state("runtime_last_connector_completion_at", self._last_connector_completion_at)
        self._publish_watchdog_state()

    async def _event_loop_watchdog_loop(self) -> None:
        interval = 1.0
        while not self._shutdown_requested:
            started_at = time.monotonic()
            await asyncio.sleep(interval)
            elapsed = time.monotonic() - started_at
            self._event_loop_lag_seconds = max(0.0, elapsed - interval)
            if self._event_loop_lag_seconds >= float(
                getattr(self.settings, "watchdog_event_loop_lag_seconds", 5.0)
            ):
                self._event_loop_lag_failures += 1
            else:
                self._event_loop_lag_failures = 0
            self._record_loop_success("event_loop_watchdog")
            self._publish_watchdog_state()

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
        tasks = [
            asyncio.create_task(self._supervise_loop("imessage", self._poll_imessage_loop)),
            asyncio.create_task(self._supervise_loop("run_executor", self._run_executor_loop)),
            asyncio.create_task(self._supervise_loop("event_loop_watchdog", self._event_loop_watchdog_loop)),
        ]
        if self.mail_ingress is not None:
            tasks.append(asyncio.create_task(self._supervise_loop("mail", self._poll_mail_loop)))
        if self.reminders_ingress is not None:
            tasks.append(asyncio.create_task(self._supervise_loop("reminders", self._poll_reminders_loop)))
        if self.notes_ingress is not None:
            tasks.append(asyncio.create_task(self._supervise_loop("notes", self._poll_notes_loop)))
        if self.calendar_ingress is not None:
            tasks.append(asyncio.create_task(self._supervise_loop("calendar", self._poll_calendar_loop)))
        if self.companion is not None:
            tasks.append(asyncio.create_task(self._supervise_loop("companion", self._companion_loop)))
        if self.ambient is not None:
            tasks.append(asyncio.create_task(self._supervise_loop("ambient", self._ambient_loop)))
        if getattr(self, "memory_service", None) is not None:
            tasks.append(asyncio.create_task(self._supervise_loop("memory_maintenance", self._memory_maintenance_loop)))
        if getattr(getattr(self, "settings", None), "enable_helper_maintenance", False):
            tasks.append(asyncio.create_task(self._supervise_loop("helper_maintenance", self._helper_maintenance_loop)))
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
                self._record_loop_success("memory_maintenance")
                self._publish_watchdog_state()
            except Exception as exc:
                logger.exception("Memory maintenance loop error: %s", exc)
                self._record_loop_failure("memory_maintenance", f"{type(exc).__name__}: {exc}")
            await asyncio.sleep(self.settings.memory_v2_maintenance_interval_seconds)

    async def _helper_maintenance_loop(self) -> None:
        """Periodically recycle stale helper subprocesses when the daemon is idle."""
        logger.info(
            "Helper maintenance loop started (interval=%.0fs idle>=%.0fs age>=%.0fs)",
            self.settings.helper_maintenance_interval_seconds,
            self.settings.helper_recycle_idle_seconds,
            self.settings.helper_recycle_max_age_seconds,
        )
        while not self._shutdown_requested:
            try:
                result = self.recycle_helpers(False)
                logger.info("Helper maintenance check: %s", result)
                self._record_loop_success("helper_maintenance")
                self._publish_watchdog_state()
            except Exception as exc:
                logger.exception("Helper maintenance loop error: %s", exc)
                self._record_loop_failure("helper_maintenance", f"{type(exc).__name__}: {exc}")
            await asyncio.sleep(self.settings.helper_maintenance_interval_seconds)

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
                messages = await asyncio.to_thread(
                    self.ingress.fetch_new,
                    since_rowid=self._last_rowid,
                    sender_allowlist=sender_allowlist,
                    require_sender_filter=self.settings.only_poll_allowed_senders,
                )
                recent_attachment_outbound = getattr(
                    self.egress,
                    "was_recent_attachment_outbound",
                    lambda _sender: False,
                )

                # Update in-memory cursor for all fetched messages; write to DB once after batch
                dispatchable = []
                for msg in messages:
                    if self._shutdown_requested:
                        break
                    self._last_rowid = max(int(msg.id), self._last_rowid or 0)
                    if msg.is_from_me:
                        continue
                    has_attachments = bool((msg.context or {}).get("attachments"))
                    placeholder_only = (msg.text or "").strip() in _ATTACHMENT_PLACEHOLDER_TEXTS
                    if placeholder_only and recent_attachment_outbound(msg.sender):
                        logger.info(
                            "Ignoring probable outbound attachment placeholder echo from %s (rowid=%s)",
                            msg.sender,
                            msg.id,
                        )
                        continue
                    if not msg.text.strip() and not has_attachments:
                        logger.info("Ignoring empty inbound rowid=%s sender=%s", msg.id, msg.sender)
                        continue
                    if not msg.text.strip() and has_attachments:
                        msg.text = await asyncio.to_thread(self._synthesize_attachment_only_text, msg)
                        logger.info(
                            "Synthesized text for attachment-only inbound rowid=%s sender=%s text=%r",
                            msg.id,
                            msg.sender,
                            msg.text,
                        )
                    if has_attachments and recent_attachment_outbound(msg.sender):
                        logger.info("Ignoring probable outbound attachment echo from %s (rowid=%s)", msg.sender, msg.id)
                        continue
                    if self._consume_restart_echo_suppress(msg.sender, msg.text):
                        logger.info("Ignoring restart confirmation echo from %s (rowid=%s)", msg.sender, msg.id)
                        continue
                    if self._consume_companion_echo_suppress(msg.sender, msg.text):
                        logger.info("Ignoring companion-originated echo from %s (rowid=%s)", msg.sender, msg.id)
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
                            await self._send_via_egress(
                                msg.sender,
                                "Apple Flow: sender not authorized for this relay.",
                            )
                        continue
                    if not self.policy.is_under_rate_limit(msg.sender, datetime.now(UTC)):
                        logger.info("Rate limit triggered for sender: %s", msg.sender)
                        if self.settings.notify_rate_limited_senders:
                            await self._send_via_egress(
                                msg.sender,
                                "Apple Flow: rate limit exceeded, please retry in a minute.",
                            )
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
                            self._record_connector_completion()
                        except Exception as exc:
                            logger.exception(
                                "Unhandled iMessage dispatch failure rowid=%s sender=%s: %s",
                                msg.id,
                                msg.sender,
                                exc,
                            )
                            try:
                                await self._send_via_egress(
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
                self._record_loop_success("imessage")
                self._publish_watchdog_state()
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
                self._record_loop_failure("imessage", f"{type(exc).__name__}: {exc}")

            await asyncio.sleep(self.settings.poll_interval_seconds)
        await self._flush_inflight_on_shutdown(timeout=2.0)

    def _synthesize_attachment_only_text(self, msg: InboundMessage) -> str:
        attachments = list((msg.context or {}).get("attachments") or [])
        synthetic = ""
        if attachments and getattr(self, "attachment_processor", None) is not None:
            analysis = self.attachment_processor.analyze_attachments(msg.id, attachments)
            if analysis.prompt_block:
                msg.context["attachment_prompt_block"] = analysis.prompt_block
            if analysis.metadata:
                msg.context["attachment_processing"] = analysis.metadata
            if analysis.voice_transcript:
                msg.context["voice_transcript"] = analysis.voice_transcript
            if analysis.suggested_text:
                msg.context["attachment_suggested_text"] = analysis.suggested_text
                synthetic = analysis.suggested_text
            if analysis.suggested_reason:
                msg.context["synthetic_text_reason"] = analysis.suggested_reason
            msg.context["attachment_analysis_ready"] = True
        if not synthetic:
            synthetic = "analyze attached files"
            if getattr(self.settings, "require_chat_prefix", False):
                chat_prefix = (getattr(self.settings, "chat_prefix", "relay:") or "relay:").strip()
                synthetic = f"{chat_prefix} {synthetic}"
            msg.context["synthetic_text_reason"] = "attachment_only"
        return synthetic

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
            if marker_sender == sender and normalize_echo_text(marker_text) == normalize_echo_text(text):
                self.store.set_state("system_restart_echo_suppress", "")
                return True
        except Exception:
            # Clear malformed marker to avoid repeated parse failures.
            self.store.set_state("system_restart_echo_suppress", "")
            return False
        return False

    def _consume_companion_echo_suppress(self, sender: str, text: str) -> bool:
        """Consume durable companion suppress entries and return True on match."""
        raw_markers = self.store.get_state("companion_echo_suppress")
        if not raw_markers:
            return False

        try:
            entries = json.loads(raw_markers)
        except Exception:
            self.store.set_state("companion_echo_suppress", "")
            return False
        if not isinstance(entries, list):
            self.store.set_state("companion_echo_suppress", "")
            return False

        now_ts = time.time()
        normalized_sender = normalize_sender(sender)
        normalized_text = normalize_echo_text(text)
        matched = False
        kept: list[dict[str, object]] = []

        for item in entries:
            if not isinstance(item, dict):
                continue
            item_sender = normalize_sender(str(item.get("sender", "")))
            item_text = normalize_echo_text(str(item.get("text", "")))
            try:
                expires_at = float(item.get("expires_at", 0))
            except (TypeError, ValueError):
                expires_at = 0.0
            if expires_at <= now_ts:
                continue

            if not matched and item_sender == normalized_sender and item_text == normalized_text:
                matched = True
                continue

            kept.append({
                "sender": item_sender,
                "text": str(item.get("text", "")),
                "expires_at": expires_at,
            })

        if matched:
            self.store.set_state("companion_echo_suppress", json.dumps(kept) if kept else "")
        elif len(kept) != len(entries):
            # Prune expired/invalid entries even when no message matched.
            self.store.set_state("companion_echo_suppress", json.dumps(kept) if kept else "")

        return matched

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
                messages = await asyncio.to_thread(
                    self.mail_ingress.fetch_new,
                    sender_allowlist=mail_allowlist,
                    require_sender_filter=bool(mail_allowlist),
                )
                if getattr(self.mail_ingress, "last_fetch_error", ""):
                    self._record_gateway_failure("mail", self.mail_ingress.last_fetch_error)
                else:
                    self._record_gateway_success("mail")
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
                                await self._send_via_egress(self._mail_owner, imsg)
                            self._record_connector_completion()
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
                self._record_loop_success("mail")
                self._publish_watchdog_state()
            except Exception as exc:
                logger.exception("Mail polling loop error: %s", exc)
                self._record_loop_failure("mail", f"{type(exc).__name__}: {exc}")

            await asyncio.sleep(self.settings.poll_interval_seconds)
        await self._flush_inflight_on_shutdown(timeout=2.0)

    async def _poll_reminders_loop(self) -> None:
        """Apple Reminders polling loop — runs alongside iMessage/Mail when enabled."""
        assert self.reminders_ingress is not None
        assert self.reminders_egress is not None
        assert self.reminders_orchestrator is not None

        logger.info("Apple Reminders polling loop started (list=%r)", self.settings.reminders_list_name)
        gate_active = False
        while not self._shutdown_requested:
            try:
                if reminders_runtime_gate.is_reminders_polling_paused():
                    if not gate_active:
                        gate_active = True
                        logger.info("Reminders polling paused: live automation gate is active")
                    self._record_gateway_success("reminders")
                    self._record_loop_success("reminders")
                    self._publish_watchdog_state()
                else:
                    if gate_active:
                        gate_active = False
                        logger.info("Reminders polling resumed: live automation gate cleared")

                    messages = await asyncio.to_thread(self.reminders_ingress.fetch_new)
                    if getattr(self.reminders_ingress, "last_fetch_error", ""):
                        self._record_gateway_failure("reminders", self.reminders_ingress.last_fetch_error)
                    else:
                        self._record_gateway_success("reminders")
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

                        dispatchable_reminders.append(msg)

                    async def _dispatch_reminder(msg):
                        async with self._concurrency_sem:
                            try:
                                started_at = time.monotonic()
                                result = await asyncio.to_thread(self.reminders_orchestrator.handle_message, msg)
                                duration = time.monotonic() - started_at
                                reminder_id = msg.context.get("reminder_id", "")
                                occurrence_key = msg.context.get("occurrence_key", "") or f"{reminder_id}|"
                                logger.info(
                                    "Handled reminder id=%s kind=%s run_id=%s duration=%.2fs",
                                    msg.id,
                                    result.kind.value,
                                    result.run_id,
                                    duration,
                                )
                                if result.response and reminder_id:
                                    if result.kind.value in ("task", "project"):
                                        await self._call_blocking(
                                            self.reminders_egress.annotate_reminder,
                                            reminder_id,
                                            f"[Apple Flow] Awaiting approval — check iMessage.\n\n{result.response[:500]}",
                                        )
                                    else:
                                        list_name = msg.context.get("list_name", self.settings.reminders_list_name)
                                        await self._call_blocking(
                                            self.reminders_egress.move_to_archive,
                                            reminder_id=reminder_id,
                                            result_text=f"[Apple Flow Result]\n\n{result.response}",
                                            source_list_name=list_name,
                                            archive_list_name=self.settings.reminders_archive_list_name,
                                        )
                                if occurrence_key:
                                    self.reminders_ingress.mark_processed_occurrence(occurrence_key)
                                self._record_connector_completion()
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
                    self._record_loop_success("reminders")
                    self._publish_watchdog_state()
            except Exception as exc:
                logger.exception("Reminders polling loop error: %s", exc)
                self._record_loop_failure("reminders", f"{type(exc).__name__}: {exc}")

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
                if getattr(self.notes_ingress, "last_fetch_error", ""):
                    self._record_gateway_failure("notes", self.notes_ingress.last_fetch_error)
                else:
                    self._record_gateway_success("notes")
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
                                    await self._call_blocking(
                                        self.notes_egress.append_result,
                                        note_id,
                                        "[Apple Flow] Awaiting approval — check iMessage to approve/deny.",
                                    )
                                else:
                                    await self._call_blocking(
                                        self.notes_egress.move_to_archive,
                                        note_id=note_id,
                                        result_text=f"\n\n[Apple Flow Result]\n{result.response}",
                                        source_folder_name=folder_name,
                                        archive_subfolder_name=self.settings.notes_archive_folder_name,
                                    )
                            # Mark processed only after the run path completes so failed runs can be retried.
                            if note_id:
                                self.notes_ingress.mark_processed(note_id)
                            self._record_connector_completion()
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
                self._record_loop_success("notes")
                self._publish_watchdog_state()
            except Exception as exc:
                logger.exception("Notes polling loop error: %s", exc)
                self._record_loop_failure("notes", f"{type(exc).__name__}: {exc}")

            await asyncio.sleep(self.settings.notes_poll_interval_seconds)

    async def _poll_calendar_loop(self) -> None:
        """Apple Calendar polling loop."""
        assert self.calendar_ingress is not None
        assert self.calendar_egress is not None
        assert self.calendar_orchestrator is not None

        logger.info("Apple Calendar polling loop started (calendar=%r)", self.settings.calendar_name)
        while not self._shutdown_requested:
            try:
                messages = await asyncio.to_thread(self.calendar_ingress.fetch_new)
                if getattr(self.calendar_ingress, "last_fetch_error", ""):
                    self._record_gateway_failure("calendar", self.calendar_ingress.last_fetch_error)
                else:
                    self._record_gateway_success("calendar")
                dispatchable_calendar = []
                for msg in messages:
                    if self._shutdown_requested:
                        break
                    if not msg.text.strip():
                        continue

                    event_id = msg.context.get("event_id", "")
                    event_summary = msg.context.get("event_summary", "")
                    logger.info("Inbound calendar event id=%s summary=%r chars=%s", msg.id, event_summary, len(msg.text))

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
                                    await self._call_blocking(
                                        self.calendar_egress.annotate_event,
                                        event_id,
                                        "[Apple Flow] Awaiting approval — check iMessage to approve/deny.",
                                    )
                                else:
                                    await self._call_blocking(
                                        self.calendar_egress.annotate_event,
                                        event_id,
                                        result.response,
                                    )
                            if event_id:
                                self.calendar_ingress.mark_processed(event_id)
                            self._record_connector_completion()
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
                self._record_loop_success("calendar")
                self._publish_watchdog_state()
            except Exception as exc:
                logger.exception("Calendar polling loop error: %s", exc)
                self._record_loop_failure("calendar", f"{type(exc).__name__}: {exc}")

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
        elif connector_type == "ollama":
            model_val = self.settings.ollama_model or "ollama default"
            connector_line = "⚙️  Engine: ollama /api/chat (native, local)"
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
