from __future__ import annotations

import asyncio
import logging
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
from .codex_connector import CodexAppServerConnector
from .companion import CompanionLoop
from .config import RelaySettings
from .egress import IMessageEgress
from .gateways import (
    CalendarGateway,
    IMessageGateway,
    MailGateway,
    NotesGateway,
    RemindersGateway,
)
from .ingress import IMessageIngress
from .mail_egress import AppleMailEgress
from .mail_ingress import AppleMailIngress
from .memory import FileMemory
from .notes_egress import AppleNotesEgress
from .notes_ingress import AppleNotesIngress
from .office_sync import OfficeSyncer
from .orchestrator import RelayOrchestrator
from .policy import PolicyEngine
from .protocols import ConnectorProtocol
from .reminders_egress import AppleRemindersEgress
from .reminders_ingress import AppleRemindersIngress
from .scheduler import FollowUpScheduler
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.daemon")


class RelayDaemon:
    def __init__(self, settings: RelaySettings):
        self.settings = settings
        self._init_core()
        self._init_connector()
        self._init_office_and_memory()
        self._init_companion_and_ambient()
        self._init_gateways()
        self._init_runtime_state()

    def _init_core(self) -> None:
        self.store = SQLiteStore(Path(self.settings.db_path))
        self.store.bootstrap()
        self.policy = PolicyEngine(self.settings)
        self.ingress = IMessageIngress(
            self.settings.messages_db_path,
            enable_attachments=self.settings.enable_attachments,
            max_attachment_size_mb=self.settings.max_attachment_size_mb,
        )
        self.egress = IMessageEgress(
            suppress_duplicate_outbound_seconds=self.settings.suppress_duplicate_outbound_seconds
        )

    def _init_connector(self) -> None:
        connector_type = self.settings.get_connector_type()
        known_connectors = {"codex-cli", "claude-cli", "cline", "codex-app-server"}
        if connector_type not in known_connectors:
            raise ValueError(
                f"Unknown connector type: {connector_type!r}. "
                f"Valid options: {', '.join(sorted(known_connectors))}"
            )

        if connector_type == "codex-app-server":
            logger.warning(
                "app-server connector is deprecated and may cause state corruption. "
                "Set apple_flow_connector=codex-cli or apple_flow_connector=claude-cli instead."
            )
            self.connector: ConnectorProtocol = CodexAppServerConnector(
                self.settings.codex_app_server_cmd,
                turn_timeout_seconds=self.settings.codex_turn_timeout_seconds,
            )
        elif connector_type == "claude-cli":
            self.connector = ClaudeCliConnector(
                claude_command=self.settings.claude_cli_command,
                workspace=self.settings.default_workspace,
                timeout=self.settings.codex_turn_timeout_seconds,
                context_window=self.settings.claude_cli_context_window,
                model=self.settings.claude_cli_model,
                dangerously_skip_permissions=self.settings.claude_cli_dangerously_skip_permissions,
                tools=self.settings.claude_cli_tools,
                allowed_tools=self.settings.claude_cli_allowed_tools,
                inject_tools_context=self.settings.inject_tools_context,
                system_prompt=self.settings.personality_prompt.replace(
                    "{workspace}", self.settings.default_workspace
                ),
            )
        elif connector_type == "cline":
            self.connector = ClineConnector(
                cline_command=self.settings.cline_command,
                workspace=self.settings.default_workspace,
                timeout=self.settings.codex_turn_timeout_seconds,
                context_window=self.settings.cline_context_window,
                model=self.settings.cline_model,
                use_json=self.settings.cline_use_json,
                act_mode=self.settings.cline_act_mode,
            )
        else:  # codex-cli
            self.connector = CodexCliConnector(
                codex_command=self.settings.codex_cli_command,
                workspace=self.settings.default_workspace,
                timeout=self.settings.codex_turn_timeout_seconds,
                context_window=self.settings.codex_cli_context_window,
                model=self.settings.codex_cli_model,
                inject_tools_context=self.settings.inject_tools_context,
            )
        logger.info("Using %s connector", connector_type)

    def _init_office_and_memory(self) -> None:
        # Read SOUL.md
        self._soul_prompt = ""
        soul_path = Path(self.settings.soul_file)
        if not soul_path.is_absolute():
            soul_path = Path(__file__).resolve().parents[2] / self.settings.soul_file

        if soul_path.exists():
            try:
                self._soul_prompt = soul_path.read_text(encoding="utf-8").strip()
                logger.info("Loaded SOUL.md from %s (%d chars)", soul_path, len(self._soul_prompt))
            except Exception as exc:
                logger.warning("Failed to read SOUL.md at %s: %s", soul_path, exc)

        if self._soul_prompt and hasattr(self.connector, "set_soul_prompt"):
            self.connector.set_soul_prompt(self._soul_prompt)

        self._office_path = soul_path.parent if self._soul_prompt else None

        # Memory
        self.memory = None
        if self.settings.enable_memory and self._office_path:
            self.memory = FileMemory(self._office_path, max_context_chars=self.settings.memory_max_context_chars)

        # Scheduler
        self.scheduler = None
        if self.settings.enable_follow_ups:
            self.scheduler = FollowUpScheduler(self.store)

        # Sync
        self.office_syncer = None
        if self.settings.enable_office_sync and self.settings.supabase_service_key and self._office_path:
            self.office_syncer = OfficeSyncer(
                office_path=self._office_path,
                supabase_url=self.settings.supabase_url,
                service_key=self.settings.supabase_service_key,
            )

    def _init_companion_and_ambient(self) -> None:
        self.companion = None
        if self.settings.enable_companion:
            owner = self.settings.allowed_senders[0] if self.settings.allowed_senders else ""
            if owner:
                self.companion = CompanionLoop(
                    connector=self.connector,
                    egress=self.egress,
                    store=self.store,
                    owner=owner,
                    soul_prompt=self._soul_prompt,
                    office_path=self._office_path,
                    config=self.settings,
                    scheduler=self.scheduler,
                    memory=self.memory,
                    syncer=self.office_syncer,
                )
            else:
                logger.warning("Companion enabled but no allowed_senders configured — skipping")

        self.ambient = None
        if self.settings.enable_ambient_scanning and self.memory:
            self.ambient = AmbientScanner(
                memory=self.memory,
                scan_interval_seconds=self.settings.ambient_scan_interval_seconds,
            )

    def _init_gateways(self) -> None:
        self.gateways: list[Any] = []

        # Notes logging egress (write-only)
        notes_log_egress_obj = AppleNotesEgress(folder_name=self.settings.notes_log_folder_name) if self.settings.enable_notes_logging else None

        # Base orchestrator params
        orchestrator_kwargs = dict(
            connector=self.connector,
            store=self.store,
            allowed_workspaces=self.settings.allowed_workspaces,
            default_workspace=self.settings.default_workspace,
            approval_ttl_minutes=self.settings.approval_ttl_minutes,
            chat_prefix=self.settings.chat_prefix,
            workspace_aliases=self.settings.get_workspace_aliases(),
            auto_context_messages=self.settings.auto_context_messages,
            enable_progress_streaming=self.settings.enable_progress_streaming,
            progress_update_interval_seconds=self.settings.progress_update_interval_seconds,
            enable_verifier=self.settings.enable_verifier,
            enable_attachments=self.settings.enable_attachments,
            personality_prompt=self.settings.personality_prompt,
            shutdown_callback=self.request_shutdown,
            log_notes_egress=notes_log_egress_obj,
            notes_log_folder_name=self.settings.notes_log_folder_name,
            memory=self.memory,
            scheduler=self.scheduler,
            office_syncer=self.office_syncer,
            log_file_path=self.settings.log_file_path,
        )

        # Primary Orchestrator (iMessage + cross-channel cleanup)
        reminders_egress_obj = AppleRemindersEgress(list_name=self.settings.reminders_list_name) if self.settings.enable_reminders_polling else None
        notes_egress_obj = AppleNotesEgress(folder_name=self.settings.notes_folder_name) if self.settings.enable_notes_polling else None
        calendar_egress_obj = AppleCalendarEgress(calendar_name=self.settings.calendar_name) if self.settings.enable_calendar_polling else None

        self.orchestrator = RelayOrchestrator(
            egress=self.egress,
            require_chat_prefix=self.settings.require_chat_prefix,
            reminders_egress=reminders_egress_obj,
            reminders_archive_list_name=self.settings.reminders_archive_list_name,
            notes_egress=notes_egress_obj,
            notes_archive_folder_name=self.settings.notes_archive_folder_name,
            calendar_egress=calendar_egress_obj,
            **orchestrator_kwargs,
        )

        # iMessage Gateway (Always)
        self._imessage_gateway = IMessageGateway(
            self.settings, self.orchestrator, self.ingress, self.egress, self.policy, self.store, datetime.now(UTC)
        )
        self.gateways.append(self._imessage_gateway)

        # Apple Mail
        if self.settings.enable_mail_polling:
            mail_ingress = AppleMailIngress(
                account=self.settings.mail_poll_account,
                mailbox=self.settings.mail_poll_mailbox,
                max_age_days=self.settings.mail_max_age_days,
                trigger_tag=self.settings.trigger_tag,
            )
            mail_egress = AppleMailEgress(
                from_address=self.settings.mail_from_address,
                signature=self.settings.mail_signature,
            )
            mail_owner = self.settings.allowed_senders[0] if self.settings.allowed_senders else ""
            mail_orchestrator = RelayOrchestrator(
                egress=mail_egress,
                require_chat_prefix=self.settings.require_chat_prefix,
                approval_sender_override=mail_owner,
                **orchestrator_kwargs,
            )
            self.gateways.append(MailGateway(self.settings, mail_orchestrator, mail_ingress, mail_egress, self.egress, mail_owner))

        # Apple Reminders
        if self.settings.enable_reminders_polling:
            owner = self.settings.reminders_owner or (self.settings.allowed_senders[0] if self.settings.allowed_senders else "")
            reminders_ingress = AppleRemindersIngress(
                list_name=self.settings.reminders_list_name,
                owner_sender=owner,
                auto_approve=self.settings.reminders_auto_approve,
                trigger_tag=self.settings.trigger_tag,
                store=self.store,
            )
            reminders_orchestrator = RelayOrchestrator(
                egress=self.egress,
                require_chat_prefix=False,
                **orchestrator_kwargs,
            )
            self.gateways.append(RemindersGateway(self.settings, reminders_orchestrator, reminders_ingress, reminders_egress_obj))

        # Apple Notes
        if self.settings.enable_notes_polling:
            owner = self.settings.notes_owner or (self.settings.allowed_senders[0] if self.settings.allowed_senders else "")
            notes_ingress = AppleNotesIngress(
                folder_name=self.settings.notes_folder_name,
                trigger_tag=self.settings.trigger_tag,
                owner_sender=owner,
                auto_approve=self.settings.notes_auto_approve,
                fetch_timeout_seconds=self.settings.notes_fetch_timeout_seconds,
                fetch_retries=self.settings.notes_fetch_retries,
                fetch_retry_delay_seconds=self.settings.notes_fetch_retry_delay_seconds,
                store=self.store,
            )
            notes_orchestrator = RelayOrchestrator(
                egress=self.egress,
                require_chat_prefix=False,
                **orchestrator_kwargs,
            )
            self.gateways.append(NotesGateway(self.settings, notes_orchestrator, notes_ingress, notes_egress_obj))

        # Apple Calendar
        if self.settings.enable_calendar_polling:
            owner = self.settings.calendar_owner or (self.settings.allowed_senders[0] if self.settings.allowed_senders else "")
            calendar_ingress = AppleCalendarIngress(
                calendar_name=self.settings.calendar_name,
                owner_sender=owner,
                auto_approve=self.settings.calendar_auto_approve,
                lookahead_minutes=self.settings.calendar_lookahead_minutes,
                trigger_tag=self.settings.trigger_tag,
                store=self.store,
            )
            calendar_orchestrator = RelayOrchestrator(
                egress=self.egress,
                require_chat_prefix=False,
                **orchestrator_kwargs,
            )
            self.gateways.append(CalendarGateway(self.settings, calendar_orchestrator, calendar_ingress, calendar_egress_obj))

    def _init_runtime_state(self) -> None:
        self._concurrency_sem = asyncio.Semaphore(self.settings.max_concurrent_ai_calls)
        self._shutdown_requested = False

        # Record daemon start time
        startup_time = datetime.now(UTC)
        self.store.set_state("daemon_started_at", startup_time.isoformat())

        # Initialize iMessage cursor
        persisted_cursor = self.store.get_state("last_rowid")
        last_rowid = int(persisted_cursor) if persisted_cursor is not None else None
        latest = self.ingress.latest_rowid()

        if latest is not None and not self.settings.process_historical_on_first_start:
            if last_rowid is None:
                last_rowid = latest
                self.store.set_state("last_rowid", str(latest))
                logger.info("Initialized cursor to latest rowid=%s", latest)
            elif (latest - last_rowid) > max(0, self.settings.max_startup_replay_rows):
                logger.info("Fast-forwarding stale cursor from %s to %s", last_rowid, latest)
                last_rowid = latest
                self.store.set_state("last_rowid", str(latest))

        self._imessage_gateway.set_cursor(last_rowid)

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the daemon."""
        logger.info("Shutdown requested")
        self._shutdown_requested = True

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
        logger.info("Shutdown complete")

    async def run_forever(self) -> None:
        tasks = []
        for gateway in self.gateways:
            tasks.append(gateway.run_loop(lambda: self._shutdown_requested, self._concurrency_sem))

        if self.companion is not None:
            tasks.append(self._companion_loop())
        if self.ambient is not None:
            tasks.append(self._ambient_loop())

        await asyncio.gather(*tasks)

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


    def send_startup_intro(self) -> None:
        if not self.settings.allowed_senders:
            logger.info("Startup intro skipped: no allowed_senders configured.")
            return
        recipient = self.settings.allowed_senders[0]

        connector_type = self.settings.get_connector_type()
        if connector_type == "claude-cli":
            model_val = self.settings.claude_cli_model or "claude default"
            connector_line = "⚙️  Engine: claude -p (stateless)"
        elif connector_type == "cline":
            model_val = self.settings.cline_model or "cline default"
            connector_line = "⚙️  Engine: cline -y (agentic)"
        elif connector_type == "codex-app-server":
            model_val = self.settings.codex_cli_model or "codex default"
            connector_line = "⚙️  Engine: app-server (stateful, deprecated)"
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
            "✅ approve <id>  |  ❌ deny <id>  |  ❌❌ deny all  |  📊 status",
            "🏥 health  |  🔍 history: [query]  |  📈 usage  |  📋 logs  |  🔄 clear context",
            "🔧 system: stop  |  system: restart",
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
    finally:
        daemon.shutdown()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run())
