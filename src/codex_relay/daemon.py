from __future__ import annotations

import asyncio
import logging
import signal
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from .codex_cli_connector import CodexCliConnector
from .codex_connector import CodexAppServerConnector
from .config import RelaySettings
from .egress import IMessageEgress
from .ingress import IMessageIngress
from .mail_egress import AppleMailEgress
from .mail_ingress import AppleMailIngress
from .orchestrator import RelayOrchestrator
from .policy import PolicyEngine
from .protocols import ConnectorProtocol
from .store import SQLiteStore

logger = logging.getLogger("codex_relay.daemon")


class RelayDaemon:
    def __init__(self, settings: RelaySettings):
        self.settings = settings
        self.store = SQLiteStore(Path(settings.db_path))
        self.store.bootstrap()
        self.policy = PolicyEngine(settings)
        self.ingress = IMessageIngress(settings.messages_db_path)
        self.egress = IMessageEgress(
            suppress_duplicate_outbound_seconds=settings.suppress_duplicate_outbound_seconds
        )

        # Choose connector based on configuration
        if settings.use_codex_cli:
            logger.info("Using CLI connector (codex exec) for stateless execution")
            self.connector: ConnectorProtocol = CodexCliConnector(
                codex_command=settings.codex_cli_command,
                workspace=settings.default_workspace,
                timeout=settings.codex_turn_timeout_seconds,
                context_window=settings.codex_cli_context_window,
            )
        else:
            logger.info("Using app-server connector (JSON-RPC with persistent threads)")
            self.connector = CodexAppServerConnector(
                settings.codex_app_server_cmd,
                turn_timeout_seconds=settings.codex_turn_timeout_seconds,
            )
        self.orchestrator = RelayOrchestrator(
            connector=self.connector,
            egress=self.egress,
            store=self.store,
            allowed_workspaces=settings.allowed_workspaces,
            default_workspace=settings.default_workspace,
            approval_ttl_minutes=settings.approval_ttl_minutes,
            require_chat_prefix=settings.require_chat_prefix,
            chat_prefix=settings.chat_prefix,
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
            )
            self.mail_egress = AppleMailEgress(
                from_address=settings.mail_from_address,
            )
            # Mail gets its own orchestrator so replies route through email egress
            self.mail_orchestrator = RelayOrchestrator(
                connector=self.connector,
                egress=self.mail_egress,
                store=self.store,
                allowed_workspaces=settings.allowed_workspaces,
                default_workspace=settings.default_workspace,
                approval_ttl_minutes=settings.approval_ttl_minutes,
                require_chat_prefix=settings.require_chat_prefix,
                chat_prefix=settings.chat_prefix,
            )

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
        await asyncio.gather(*tasks)

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
                        "Update codex_relay_messages_db_path in .env and ensure Messages is enabled on this Mac."
                    )
                    await asyncio.sleep(self.settings.poll_interval_seconds)
                    continue
                messages = self.ingress.fetch_new(
                    since_rowid=self._last_rowid,
                    sender_allowlist=sender_allowlist,
                    require_sender_filter=self.settings.only_poll_allowed_senders,
                )
                for msg in messages:
                    if self._shutdown_requested:
                        break
                    self._last_rowid = max(int(msg.id), self._last_rowid or 0)
                    try:
                        self.store.set_state("last_rowid", str(self._last_rowid))
                    except sqlite3.OperationalError as exc:
                        self._throttled_state_db_warning(
                            f"State DB write failed ({exc}). Check codex_relay_db_path and filesystem permissions."
                        )
                        continue
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
                            self.egress.send(msg.sender, "Codex Relay: sender not authorized for this relay.")
                        continue
                    if not self.policy.is_under_rate_limit(msg.sender, datetime.now(UTC)):
                        logger.info("Rate limit triggered for sender: %s", msg.sender)
                        if self.settings.notify_rate_limited_senders:
                            self.egress.send(msg.sender, "Codex Relay: rate limit exceeded, please retry in a minute.")
                        continue
                    started_at = time.monotonic()
                    result = self.orchestrator.handle_message(msg)
                    duration = time.monotonic() - started_at
                    if result.response in {"ignored_empty", "ignored_missing_chat_prefix"}:
                        logger.info(
                            "Ignored rowid=%s sender=%s reason=%s",
                            msg.id,
                            msg.sender,
                            result.response,
                        )
                        continue
                    logger.info(
                        "Handled rowid=%s sender=%s kind=%s run_id=%s duration=%.2fs",
                        msg.id,
                        msg.sender,
                        result.kind.value,
                        result.run_id,
                        duration,
                    )
            except sqlite3.OperationalError as exc:
                if "unable to open database file" in str(exc).lower():
                    self._throttled_messages_db_warning(
                        f"Messages DB open failed ({exc}). Grant Terminal Full Disk Access and verify "
                        f"codex_relay_messages_db_path={self.settings.messages_db_path} "
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
                    started_at = time.monotonic()
                    result = self.mail_orchestrator.handle_message(msg)
                    duration = time.monotonic() - started_at
                    if result.response in {"ignored_empty", "ignored_missing_chat_prefix"}:
                        logger.info(
                            "Ignored email id=%s sender=%s reason=%s",
                            msg.id,
                            msg.sender,
                            result.response,
                        )
                        continue
                    logger.info(
                        "Handled email id=%s sender=%s kind=%s run_id=%s duration=%.2fs",
                        msg.id,
                        msg.sender,
                        result.kind.value,
                        result.run_id,
                        duration,
                    )
            except Exception as exc:
                logger.exception("Mail polling loop error: %s", exc)

            await asyncio.sleep(self.settings.poll_interval_seconds)

    def send_startup_intro(self) -> None:
        if not self.settings.allowed_senders:
            logger.info("Startup intro skipped: no allowed_senders configured.")
            return
        recipient = self.settings.allowed_senders[0]
        commands = [
            f"{self.settings.chat_prefix} <message> (general chat)",
            "idea: <prompt>",
            "plan: <goal>",
            "task: <instruction> (approval required)",
            "project: <spec> (approval required)",
            "approve <request_id> / deny <request_id>",
            "status",
            "clear context (or: new chat / reset context)",
        ]
        intro = (
            "Codex-Flow is online\n"
            f"Workspace: {self.settings.default_workspace}\n"
            f"Allowed sender mode: {self.settings.only_poll_allowed_senders}\n"
            "Commands:\n- " + "\n- ".join(commands)
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

    logger.info(
        "Codex Relay running (foreground). Allowed senders=%s, strict_sender_poll=%s, messages_db=%s, mail_enabled=%s",
        len(settings.allowed_senders),
        settings.only_poll_allowed_senders,
        settings.messages_db_path,
        settings.enable_mail_polling,
    )
    if settings.send_startup_intro:
        daemon.send_startup_intro()
    channels = "iMessages"
    if settings.enable_mail_polling:
        channels += " + Apple Mail"
    logger.info("Ready. Waiting for inbound %s. Press Ctrl+C to stop.", channels)

    try:
        await daemon.run_forever()
    finally:
        daemon.shutdown()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run())
