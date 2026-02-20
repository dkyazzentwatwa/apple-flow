from __future__ import annotations

import asyncio
import logging
import signal
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from .calendar_egress import AppleCalendarEgress
from .calendar_ingress import AppleCalendarIngress
from .claude_cli_connector import ClaudeCliConnector
from .cline_connector import ClineConnector
from .codex_cli_connector import CodexCliConnector
from .codex_connector import CodexAppServerConnector
from .ambient import AmbientScanner
from .companion import CompanionLoop
from .office_sync import OfficeSyncer
from .config import RelaySettings
from .egress import IMessageEgress
from .ingress import IMessageIngress
from .mail_egress import AppleMailEgress
from .mail_ingress import AppleMailIngress
from .memory import FileMemory
from .notes_egress import AppleNotesEgress
from .notes_ingress import AppleNotesIngress
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
        connector_type = settings.get_connector_type()
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
            logger.info("Using app-server connector (JSON-RPC with persistent threads)")
            self.connector: ConnectorProtocol = CodexAppServerConnector(
                settings.codex_app_server_cmd,
                turn_timeout_seconds=settings.codex_turn_timeout_seconds,
            )
        elif connector_type == "claude-cli":
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

        # Inject soul prompt into connector (both claude-cli and codex-cli support it)
        if self._soul_prompt and hasattr(self.connector, "set_soul_prompt"):
            self.connector.set_soul_prompt(self._soul_prompt)

        # Resolve agent-office path for companion/memory
        self._office_path = soul_path.parent if self._soul_prompt else None

        # File-based memory (reads/writes agent-office MEMORY.md + 60_memory/)
        self.memory: FileMemory | None = None
        if settings.enable_memory and self._office_path:
            self.memory = FileMemory(self._office_path, max_context_chars=settings.memory_max_context_chars)
            logger.info("File-based memory enabled (office=%s)", self._office_path)

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
            enable_verifier=settings.enable_verifier,
            enable_attachments=settings.enable_attachments,
            personality_prompt=settings.personality_prompt,
            shutdown_callback=self.request_shutdown,
            log_notes_egress=notes_log_egress_obj,
            notes_log_folder_name=settings.notes_log_folder_name,
            memory=self.memory,
            scheduler=self.scheduler,
            office_syncer=self.office_syncer,
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
                signature=settings.mail_signature,
            )
            self.mail_orchestrator = RelayOrchestrator(
                egress=self.mail_egress,
                require_chat_prefix=settings.require_chat_prefix,
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

        self._concurrency_sem = asyncio.Semaphore(settings.max_concurrent_ai_calls)

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

        # Record daemon start time for health dashboard
        self.store.set_state("daemon_started_at", datetime.now(UTC).isoformat())

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
        tasks = [self._poll_imessage_loop()]
        if self.mail_ingress is not None:
            tasks.append(self._poll_mail_loop())
        if self.reminders_ingress is not None:
            tasks.append(self._poll_reminders_loop())
        if self.notes_ingress is not None:
            tasks.append(self._poll_notes_loop())
        if self.calendar_ingress is not None:
            tasks.append(self._poll_calendar_loop())
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
                    async with self._concurrency_sem:
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

                if dispatchable:
                    await asyncio.gather(
                        *[asyncio.create_task(_dispatch_imessage(msg)) for msg in dispatchable],
                        return_exceptions=True,
                    )
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

    async def _poll_mail_loop(self) -> None:
        """Apple Mail polling loop — runs alongside iMessage when enabled."""
        assert self.mail_ingress is not None
        assert self.mail_egress is not None
        assert self.mail_orchestrator is not None

        logger.info("Apple Mail polling loop started")
        while not self._shutdown_requested:
            try:
                mail_allowlist = self.settings.mail_allowed_senders or None
                messages = self.mail_ingress.fetch_new(
                    sender_allowlist=mail_allowlist,
                    require_sender_filter=bool(mail_allowlist),
                )
                dispatchable_mail = []
                for msg in messages:
                    if self._shutdown_requested:
                        break
                    if not msg.text.strip():
                        logger.info("Ignoring empty inbound email id=%s sender=%s", msg.id, msg.sender)
                        continue
                    logger.info(
                        "Inbound email id=%s sender=%s chars=%s text=%r",
                        msg.id,
                        msg.sender,
                        len(msg.text),
                        msg.text[:120],
                    )
                    if self.mail_egress.was_recent_outbound(msg.sender, msg.text):
                        logger.info("Ignoring probable outbound echo from %s (id=%s)", msg.sender, msg.id)
                        continue
                    dispatchable_mail.append(msg)

                async def _dispatch_mail(msg):
                    async with self._concurrency_sem:
                        started_at = time.monotonic()
                        result = await asyncio.to_thread(self.mail_orchestrator.handle_message, msg)
                        duration = time.monotonic() - started_at
                        if result.response in {"ignored_empty", "ignored_missing_chat_prefix"}:
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

                if dispatchable_mail:
                    await asyncio.gather(
                        *[asyncio.create_task(_dispatch_mail(msg)) for msg in dispatchable_mail],
                        return_exceptions=True,
                    )
            except Exception as exc:
                logger.exception("Mail polling loop error: %s", exc)

            await asyncio.sleep(self.settings.poll_interval_seconds)

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
                    reminder_name = msg.context.get("reminder_name", "")
                    logger.info(
                        "Inbound reminder id=%s name=%r sender=%s chars=%s",
                        msg.id,
                        reminder_name,
                        msg.sender,
                        len(msg.text),
                    )

                    self.reminders_ingress.mark_processed(reminder_id)
                    dispatchable_reminders.append(msg)

                async def _dispatch_reminder(msg):
                    async with self._concurrency_sem:
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

                if dispatchable_reminders:
                    await asyncio.gather(
                        *[asyncio.create_task(_dispatch_reminder(msg)) for msg in dispatchable_reminders],
                        return_exceptions=True,
                    )
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

                    note_id = msg.context.get("note_id", "")
                    note_title = msg.context.get("note_title", "")
                    logger.info("Inbound note id=%s title=%r chars=%s", msg.id, note_title, len(msg.text))
                    dispatchable_notes.append(msg)

                async def _dispatch_note(msg):
                    async with self._concurrency_sem:
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
                                    f"[Apple Flow] Awaiting approval — check iMessage to approve/deny.",
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

                if dispatchable_notes:
                    await asyncio.gather(
                        *[asyncio.create_task(_dispatch_note(msg)) for msg in dispatchable_notes],
                        return_exceptions=True,
                    )
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
                        started_at = time.monotonic()
                        result = await asyncio.to_thread(self.calendar_orchestrator.handle_message, msg)
                        duration = time.monotonic() - started_at
                        event_id = msg.context.get("event_id", "")
                        logger.info("Handled calendar event id=%s kind=%s duration=%.2fs", msg.id, result.kind.value, duration)
                        if result.response and event_id:
                            if result.kind.value in ("task", "project"):
                                self.calendar_egress.annotate_event(
                                    event_id,
                                    f"[Apple Flow] Awaiting approval — check iMessage to approve/deny.",
                                )
                            else:
                                self.calendar_egress.annotate_event(event_id, result.response)

                if dispatchable_calendar:
                    await asyncio.gather(
                        *[asyncio.create_task(_dispatch_calendar(msg)) for msg in dispatchable_calendar],
                        return_exceptions=True,
                    )
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
            "🏥 health  |  🔍 history: [query]  |  📈 usage  |  🔄 clear context",
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
