from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable

from .models import InboundMessage
from .orchestrator import RelayOrchestrator

if TYPE_CHECKING:
    from .config import RelaySettings
    from .egress import IMessageEgress
    from .ingress import IMessageIngress
    from .protocols import EgressProtocol, StoreProtocol

logger = logging.getLogger("apple_flow.gateways")

class Gateway(ABC):
    def __init__(self, name: str, settings: RelaySettings, orchestrator: RelayOrchestrator):
        self.name = name
        self.settings = settings
        self.orchestrator = orchestrator

    @abstractmethod
    async def run_loop(self, should_shutdown: Callable[[], bool], concurrency_sem: asyncio.Semaphore) -> None:
        pass

class IMessageGateway(Gateway):
    def __init__(
        self,
        settings: RelaySettings,
        orchestrator: RelayOrchestrator,
        ingress: IMessageIngress,
        egress: IMessageEgress,
        policy: Any,
        store: StoreProtocol,
        startup_time: datetime,
    ):
        super().__init__("iMessage", settings, orchestrator)
        self.ingress = ingress
        self.egress = egress
        self.policy = policy
        self.store = store
        self.startup_time = startup_time
        self.last_rowid: int | None = None
        self._last_messages_db_error_at: float = 0.0
        self._last_state_db_error_at: float = 0.0

    def set_cursor(self, rowid: int | None) -> None:
        self.last_rowid = rowid

    async def run_loop(self, should_shutdown: Callable[[], bool], concurrency_sem: asyncio.Semaphore) -> None:
        logger.info("iMessage polling loop started")
        while not should_shutdown():
            try:
                sender_allowlist = self.settings.allowed_senders if self.settings.only_poll_allowed_senders else None
                if self.settings.only_poll_allowed_senders and not (sender_allowlist or []):
                    logger.warning("only_poll_allowed_senders=true but allowed_senders is empty; polling disabled.")
                    await asyncio.sleep(self.settings.poll_interval_seconds)
                    continue

                if not self.ingress.db_path.exists():
                    self._throttled_messages_db_warning(f"Messages DB not found at {self.ingress.db_path}")
                    await asyncio.sleep(self.settings.poll_interval_seconds)
                    continue

                messages = self.ingress.fetch_new(
                    since_rowid=self.last_rowid,
                    sender_allowlist=sender_allowlist,
                    require_sender_filter=self.settings.only_poll_allowed_senders,
                )

                dispatchable = []
                for msg in messages:
                    if should_shutdown():
                        break
                    self.last_rowid = max(int(msg.id), self.last_rowid or 0)
                    if msg.is_from_me:
                        continue
                    if not msg.text.strip():
                        continue
                    if self.egress.was_recent_outbound(msg.sender, msg.text):
                        continue

                    # Startup catch-up
                    if self.settings.startup_catchup_window_seconds > 0:
                        try:
                            msg_time = datetime.fromisoformat(msg.received_at).replace(tzinfo=UTC)
                        except Exception:
                            msg_time = None
                        if msg_time is not None:
                            cutoff = self.startup_time - timedelta(seconds=self.settings.startup_catchup_window_seconds)
                            if msg_time < cutoff:
                                continue

                    if not self.policy.is_sender_allowed(msg.sender):
                        if self.settings.notify_blocked_senders:
                            self.egress.send(msg.sender, "Apple Flow: sender not authorized.")
                        continue

                    if not self.policy.is_under_rate_limit(msg.sender, datetime.now(UTC)):
                        if self.settings.notify_rate_limited_senders:
                            self.egress.send(msg.sender, "Apple Flow: rate limit exceeded.")
                        continue

                    dispatchable.append(msg)

                if messages:
                    try:
                        self.store.set_state("last_rowid", str(self.last_rowid))
                    except Exception as exc:
                        self._throttled_state_db_warning(f"State DB write failed: {exc}")

                if dispatchable:
                    await asyncio.gather(
                        *[self._dispatch(msg, concurrency_sem) for msg in dispatchable],
                        return_exceptions=True,
                    )

            except Exception as exc:
                logger.exception("iMessage loop error: %s", exc)

            await asyncio.sleep(self.settings.poll_interval_seconds)

    async def _dispatch(self, msg: InboundMessage, sem: asyncio.Semaphore) -> None:
        async with sem:
            started_at = time.monotonic()
            result = await asyncio.to_thread(self.orchestrator.handle_message, msg)
            duration = time.monotonic() - started_at
            if result.response not in {"ignored_empty", "ignored_missing_chat_prefix"}:
                logger.info("Handled %s rowid=%s kind=%s duration=%.2fs", self.name, msg.id, result.kind.value, duration)

    def _throttled_messages_db_warning(self, message: str) -> None:
        now = time.time()
        if (now - self._last_messages_db_error_at) >= 30.0:
            logger.warning(message)
            self._last_messages_db_error_at = now

    def _throttled_state_db_warning(self, message: str) -> None:
        now = time.time()
        if (now - self._last_state_db_error_at) >= 30.0:
            logger.warning(message)
            self._last_state_db_error_at = now

class MailGateway(Gateway):
    def __init__(self, settings: RelaySettings, orchestrator: RelayOrchestrator, ingress: Any, egress: Any, imessage_egress: EgressProtocol, mail_owner: str):
        super().__init__("Mail", settings, orchestrator)
        self.ingress = ingress
        self.egress = egress
        self.imessage_egress = imessage_egress
        self.mail_owner = mail_owner

    async def run_loop(self, should_shutdown: Callable[[], bool], concurrency_sem: asyncio.Semaphore) -> None:
        logger.info("Apple Mail polling loop started")
        while not should_shutdown():
            try:
                mail_allowlist = self.settings.mail_allowed_senders or None
                messages = self.ingress.fetch_new(sender_allowlist=mail_allowlist, require_sender_filter=bool(mail_allowlist))
                dispatchable = []
                for msg in messages:
                    if should_shutdown():
                        break
                    if not msg.text.strip():
                        continue
                    if self.egress.was_recent_outbound(msg.sender, msg.text):
                        continue
                    dispatchable.append(msg)

                if dispatchable:
                    await asyncio.gather(*[self._dispatch(msg, concurrency_sem) for msg in dispatchable], return_exceptions=True)
            except Exception as exc:
                logger.exception("Mail loop error: %s", exc)
            await asyncio.sleep(self.settings.poll_interval_seconds)

    async def _dispatch(self, msg: InboundMessage, sem: asyncio.Semaphore) -> None:
        async with sem:
            started_at = time.monotonic()
            result = await asyncio.to_thread(self.orchestrator.handle_message, msg)
            duration = time.monotonic() - started_at
            if result.response not in {"ignored_empty", "ignored_missing_chat_prefix"}:
                logger.info("Handled %s id=%s kind=%s duration=%.2fs", self.name, msg.id, result.kind.value, duration)
                if self.mail_owner and result.response:
                    preview = result.response[:200]
                    prefix = "📧 Mail from " + msg.sender + (" needs approval" if result.kind.value in ("task", "project") else "")
                    self.imessage_egress.send(self.mail_owner, f"{prefix}\n\n{preview}")

class RemindersGateway(Gateway):
    def __init__(self, settings: RelaySettings, orchestrator: RelayOrchestrator, ingress: Any, egress: Any):
        super().__init__("Reminders", settings, orchestrator)
        self.ingress = ingress
        self.egress = egress

    async def run_loop(self, should_shutdown: Callable[[], bool], concurrency_sem: asyncio.Semaphore) -> None:
        logger.info("Apple Reminders polling loop started")
        while not should_shutdown():
            try:
                messages = self.ingress.fetch_new()
                dispatchable = []
                for msg in messages:
                    if should_shutdown():
                        break
                    if not msg.text.strip():
                        continue
                    self.ingress.mark_processed(msg.context.get("reminder_id", ""))
                    dispatchable.append(msg)
                if dispatchable:
                    await asyncio.gather(*[self._dispatch(msg, concurrency_sem) for msg in dispatchable], return_exceptions=True)
            except Exception as exc:
                logger.exception("Reminders loop error: %s", exc)
            await asyncio.sleep(self.settings.reminders_poll_interval_seconds)

    async def _dispatch(self, msg: InboundMessage, sem: asyncio.Semaphore) -> None:
        async with sem:
            started_at = time.monotonic()
            result = await asyncio.to_thread(self.orchestrator.handle_message, msg)
            duration = time.monotonic() - started_at
            reminder_id = msg.context.get("reminder_id", "")
            if result.response and reminder_id:
                if result.kind.value in ("task", "project"):
                    self.egress.annotate_reminder(reminder_id, f"[Apple Flow] Awaiting approval — check iMessage.\n\n{result.response[:500]}")
                else:
                    self.egress.move_to_archive(reminder_id=reminder_id, result_text=f"[Apple Flow Result]\n\n{result.response}",
                                             source_list_name=msg.context.get("list_name", self.settings.reminders_list_name),
                                             archive_list_name=self.settings.reminders_archive_list_name)
            logger.info("Handled %s id=%s kind=%s duration=%.2fs", self.name, msg.id, result.kind.value, duration)

class NotesGateway(Gateway):
    def __init__(self, settings: RelaySettings, orchestrator: RelayOrchestrator, ingress: Any, egress: Any):
        super().__init__("Notes", settings, orchestrator)
        self.ingress = ingress
        self.egress = egress

    async def run_loop(self, should_shutdown: Callable[[], bool], concurrency_sem: asyncio.Semaphore) -> None:
        logger.info("Apple Notes polling loop started")
        while not should_shutdown():
            try:
                messages = await asyncio.to_thread(self.ingress.fetch_new)
                dispatchable = []
                for msg in messages:
                    if should_shutdown():
                        break
                    if not msg.text.strip():
                        continue
                    dispatchable.append(msg)
                if dispatchable:
                    await asyncio.gather(*[self._dispatch(msg, concurrency_sem) for msg in dispatchable], return_exceptions=True)
            except Exception as exc:
                logger.exception("Notes loop error: %s", exc)
            await asyncio.sleep(self.settings.notes_poll_interval_seconds)

    async def _dispatch(self, msg: InboundMessage, sem: asyncio.Semaphore) -> None:
        async with sem:
            started_at = time.monotonic()
            result = await asyncio.to_thread(self.orchestrator.handle_message, msg)
            duration = time.monotonic() - started_at
            note_id = msg.context.get("note_id", "")
            if result.response and note_id:
                if result.kind.value in ("task", "project"):
                    self.egress.append_result(note_id, "[Apple Flow] Awaiting approval — check iMessage.")
                else:
                    self.egress.move_to_archive(note_id=note_id, result_text=f"\n\n[Apple Flow Result]\n{result.response}",
                                             source_folder_name=msg.context.get("folder_name", self.settings.notes_folder_name),
                                             archive_subfolder_name=self.settings.notes_archive_folder_name)
            if note_id:
                self.ingress.mark_processed(note_id)
            logger.info("Handled %s id=%s kind=%s duration=%.2fs", self.name, msg.id, result.kind.value, duration)

class CalendarGateway(Gateway):
    def __init__(self, settings: RelaySettings, orchestrator: RelayOrchestrator, ingress: Any, egress: Any):
        super().__init__("Calendar", settings, orchestrator)
        self.ingress = ingress
        self.egress = egress

    async def run_loop(self, should_shutdown: Callable[[], bool], concurrency_sem: asyncio.Semaphore) -> None:
        logger.info("Apple Calendar polling loop started")
        while not should_shutdown():
            try:
                messages = self.ingress.fetch_new()
                dispatchable = []
                for msg in messages:
                    if should_shutdown():
                        break
                    if not msg.text.strip():
                        continue
                    self.ingress.mark_processed(msg.context.get("event_id", ""))
                    dispatchable.append(msg)
                if dispatchable:
                    await asyncio.gather(*[self._dispatch(msg, concurrency_sem) for msg in dispatchable], return_exceptions=True)
            except Exception as exc:
                logger.exception("Calendar loop error: %s", exc)
            await asyncio.sleep(self.settings.calendar_poll_interval_seconds)

    async def _dispatch(self, msg: InboundMessage, sem: asyncio.Semaphore) -> None:
        async with sem:
            started_at = time.monotonic()
            result = await asyncio.to_thread(self.orchestrator.handle_message, msg)
            duration = time.monotonic() - started_at
            event_id = msg.context.get("event_id", "")
            if result.response and event_id:
                if result.kind.value in ("task", "project"):
                    self.egress.annotate_event(event_id, "[Apple Flow] Awaiting approval — check iMessage.")
                else:
                    self.egress.annotate_event(event_id, result.response)
            logger.info("Handled %s id=%s kind=%s duration=%.2fs", self.name, msg.id, result.kind.value, duration)
