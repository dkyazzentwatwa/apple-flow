import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from apple_flow.commanding import CommandKind
from apple_flow.daemon import RelayDaemon, gateway_resource_statuses_for_settings, migrate_legacy_db_if_needed
from apple_flow.models import InboundMessage
from apple_flow.gateway_setup import EnsureResult, GatewayResourceStatus


def _settings(**overrides):
    values = {
        "enable_reminders_polling": False,
        "enable_notes_polling": False,
        "enable_notes_logging": False,
        "enable_calendar_polling": False,
        "reminders_list_name": "agent-task",
        "reminders_archive_list_name": "agent-archive",
        "notes_folder_name": "agent-task",
        "notes_archive_folder_name": "agent-archive",
        "notes_log_folder_name": "agent-logs",
        "calendar_name": "agent-schedule",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_gateway_resource_statuses_respect_enabled_gateways(monkeypatch):
    captured = {}

    def fake_ensure_gateway_resources(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("apple_flow.daemon.ensure_gateway_resources", fake_ensure_gateway_resources)

    gateway_resource_statuses_for_settings(
        _settings(enable_reminders_polling=True, enable_notes_logging=True, enable_calendar_polling=True)
    )

    assert captured["enable_reminders"] is True
    assert captured["enable_notes"] is False
    assert captured["enable_notes_logging"] is True
    assert captured["enable_calendar"] is True


def test_relaydaemon_logs_gateway_resource_statuses(caplog, monkeypatch):
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon.settings = _settings()

    monkeypatch.setattr(
        "apple_flow.daemon.gateway_resource_statuses_for_settings",
        lambda _settings: [
            GatewayResourceStatus("Reminders task list", "agent-task", EnsureResult(status="created")),
            GatewayResourceStatus(
                "Calendar",
                "agent-schedule",
                EnsureResult(status="failed", detail="Calendar permission denied"),
            ),
        ],
    )

    caplog.set_level("INFO")
    daemon._ensure_gateway_resources()

    assert "Gateway resource ensure: Reminders task list 'agent-task': created" in caplog.text
    assert "Gateway resource ensure failed: Calendar 'agent-schedule': failed (Calendar permission denied)" in caplog.text


def test_migrate_legacy_db_when_safe(tmp_path):
    legacy_db = tmp_path / "legacy" / "relay.db"
    target_db = tmp_path / "apple-flow" / "relay.db"
    legacy_db.parent.mkdir(parents=True)
    legacy_db.write_text("legacy-db", encoding="utf-8")

    settings = SimpleNamespace(model_fields_set=set(), db_path=target_db)

    migrated = migrate_legacy_db_if_needed(
        settings,
        legacy_db_path=legacy_db,
        default_db_path=target_db,
    )

    assert migrated is True
    assert target_db.read_text(encoding="utf-8") == "legacy-db"
    assert not legacy_db.exists()


def test_migrate_legacy_db_skips_when_db_path_is_explicit(tmp_path):
    legacy_db = tmp_path / "legacy" / "relay.db"
    target_db = tmp_path / "apple-flow" / "relay.db"
    legacy_db.parent.mkdir(parents=True)
    legacy_db.write_text("legacy-db", encoding="utf-8")

    settings = SimpleNamespace(model_fields_set={"db_path"}, db_path=target_db)

    migrated = migrate_legacy_db_if_needed(
        settings,
        legacy_db_path=legacy_db,
        default_db_path=target_db,
    )

    assert migrated is False
    assert legacy_db.exists()
    assert not target_db.exists()


@pytest.mark.asyncio
async def test_mail_poll_loop_skips_forwarding_duplicate_response():
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon._shutdown_requested = False
    daemon.settings = SimpleNamespace(mail_allowed_senders=[], poll_interval_seconds=0)
    daemon._concurrency_sem = asyncio.Semaphore(2)
    daemon._mail_owner = "+15551230000"

    inbound = InboundMessage(
        id="mail_42",
        sender="user@example.com",
        text="relay: hello",
        received_at="2026-01-01T00:00:00Z",
        is_from_me=False,
    )

    daemon.mail_ingress = SimpleNamespace(fetch_new=lambda **kwargs: [inbound])
    daemon.mail_egress = SimpleNamespace(was_recent_outbound=lambda sender, text: False)
    daemon.egress = SimpleNamespace(send=lambda *args, **kwargs: sent.append(args))

    sent: list[tuple] = []

    class _FakeMailOrchestrator:
        def handle_message(self, msg):
            daemon._shutdown_requested = True
            return SimpleNamespace(kind=CommandKind.STATUS, response="duplicate", run_id=None)

    daemon.mail_orchestrator = _FakeMailOrchestrator()

    await daemon._poll_mail_loop()
    assert sent == []


@pytest.mark.asyncio
async def test_mail_poll_loop_forwards_non_duplicate_response():
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon._shutdown_requested = False
    daemon.settings = SimpleNamespace(mail_allowed_senders=[], poll_interval_seconds=0)
    daemon._concurrency_sem = asyncio.Semaphore(2)
    daemon._mail_owner = "+15551230000"

    inbound = InboundMessage(
        id="mail_43",
        sender="user@example.com",
        text="relay: hello",
        received_at="2026-01-01T00:00:00Z",
        is_from_me=False,
    )

    daemon.mail_ingress = SimpleNamespace(fetch_new=lambda **kwargs: [inbound])
    daemon.mail_egress = SimpleNamespace(was_recent_outbound=lambda sender, text: False)
    daemon.egress = SimpleNamespace(send=lambda *args, **kwargs: sent.append(args))

    sent: list[tuple] = []

    class _FakeMailOrchestrator:
        def handle_message(self, msg):
            daemon._shutdown_requested = True
            return SimpleNamespace(kind=CommandKind.CHAT, response="Helpful response", run_id=None)

    daemon.mail_orchestrator = _FakeMailOrchestrator()

    await daemon._poll_mail_loop()
    assert len(sent) == 1
    assert sent[0][0] == "+15551230000"
    assert "📧 Mail from user@example.com" in sent[0][1]


@pytest.mark.asyncio
async def test_imessage_poll_loop_worker_exception_sends_fallback_notice(caplog, tmp_path):
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon._shutdown_requested = False
    daemon._concurrency_sem = asyncio.Semaphore(2)
    daemon._last_rowid = None
    daemon._startup_time = datetime.now(UTC)
    daemon._last_messages_db_error_at = 0.0
    daemon._last_state_db_error_at = 0.0

    chat_db = tmp_path / "chat.db"
    chat_db.write_text("", encoding="utf-8")

    daemon.settings = SimpleNamespace(
        allowed_senders=["+15551234567"],
        only_poll_allowed_senders=True,
        poll_interval_seconds=0,
        messages_db_path=chat_db,
        startup_catchup_window_seconds=0,
        notify_blocked_senders=False,
        notify_rate_limited_senders=False,
    )
    daemon.ingress = SimpleNamespace(
        fetch_new=lambda **kwargs: [
            InboundMessage(
                id="1",
                sender="+15551234567",
                text="task: run it",
                received_at="2026-02-17T12:00:00Z",
                is_from_me=False,
            )
        ]
    )
    daemon.policy = SimpleNamespace(
        is_sender_allowed=lambda sender: True,
        is_under_rate_limit=lambda sender, now: True,
    )
    daemon.store = SimpleNamespace(set_state=lambda key, value: None)
    sent: list[tuple[str, str]] = []
    daemon.egress = SimpleNamespace(
        was_recent_outbound=lambda sender, text: False,
        send=lambda recipient, text: sent.append((recipient, text)),
    )

    class _ExplodingOrchestrator:
        def handle_message(self, msg):
            daemon._shutdown_requested = True
            raise RuntimeError("boom")

    daemon.orchestrator = _ExplodingOrchestrator()

    caplog.set_level("ERROR")
    await daemon._poll_imessage_loop()

    assert any("Unhandled iMessage dispatch failure rowid=1 sender=+15551234567" in rec.message for rec in caplog.records)
    assert len(sent) == 1
    assert sent[0][0] == "+15551234567"
    assert "internal error" in sent[0][1].lower()
