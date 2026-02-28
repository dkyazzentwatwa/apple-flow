import asyncio
import sqlite3
import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import apple_flow.daemon as daemon_module
from apple_flow.commanding import CommandKind
from apple_flow.config import RelaySettings
from apple_flow.daemon import (
    RelayDaemon,
    gateway_resource_statuses_for_settings,
    migrate_legacy_db_if_needed,
)
from apple_flow.gateway_setup import EnsureResult, GatewayResourceStatus
from apple_flow.models import InboundMessage


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


def test_relaydaemon_wires_gemini_approval_mode(monkeypatch, tmp_path):
    captured_kwargs: dict[str, object] = {}

    class _FakeStore:
        def __init__(self, _path):
            self._conn = sqlite3.connect(":memory:")
            self._lock = threading.Lock()

        def bootstrap(self):
            pass

        def get_state(self, _key):
            return None

        def set_state(self, _key, _value):
            pass

        def _connect(self):
            return self._conn

    class _FakeIngress:
        def __init__(self, *_args, **_kwargs):
            pass

        def latest_rowid(self):
            return None

    class _FakeOrchestrator:
        def __init__(self, *_args, **_kwargs):
            self._approval = object()

        def set_run_executor(self, _executor):
            pass

    class _FakeRunExecutor:
        def __init__(self, **_kwargs):
            pass

    class _FakeGeminiConnector:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

        def shutdown(self):
            pass

        def cancel_active_processes(self, _thread_id=None):
            return 0

    monkeypatch.setattr(daemon_module, "ensure_gateway_resources", lambda **_kwargs: [])
    monkeypatch.setattr(daemon_module, "SQLiteStore", _FakeStore)
    monkeypatch.setattr(daemon_module, "PolicyEngine", lambda _settings: object())
    monkeypatch.setattr(daemon_module, "IMessageIngress", _FakeIngress)
    monkeypatch.setattr(daemon_module, "IMessageEgress", lambda **_kwargs: object())
    monkeypatch.setattr(daemon_module, "RelayOrchestrator", _FakeOrchestrator)
    monkeypatch.setattr(daemon_module, "RunExecutor", _FakeRunExecutor)
    monkeypatch.setattr(daemon_module, "GeminiCliConnector", _FakeGeminiConnector)

    settings = RelaySettings(
        connector="gemini-cli",
        db_path=tmp_path / "relay.db",
        default_workspace=str(tmp_path),
        allowed_workspaces=[str(tmp_path)],
        soul_file=str(tmp_path / "missing_soul.md"),
        gemini_cli_approval_mode="plan",
    )

    daemon = RelayDaemon(settings)
    assert captured_kwargs["approval_mode"] == "plan"
    assert captured_kwargs["model"] == settings.gemini_cli_model
    assert daemon.connector is not None


def test_relaydaemon_initializes_memory_v2(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class _FakeStore:
        def __init__(self, _path):
            self._conn = sqlite3.connect(":memory:")
            self._lock = threading.Lock()

        def bootstrap(self):
            pass

        def get_state(self, _key):
            return None

        def set_state(self, _key, _value):
            pass

        def close(self):
            pass

    class _FakeIngress:
        def __init__(self, *_args, **_kwargs):
            pass

        def latest_rowid(self):
            return None

    class _FakeOrchestrator:
        def __init__(self, *_args, **kwargs):
            captured["orchestrator_memory_service"] = kwargs.get("memory_service")
            self._approval = object()

        def set_run_executor(self, _executor):
            pass

    class _FakeRunExecutor:
        def __init__(self, **_kwargs):
            pass

    class _FakeMemoryService:
        def __init__(self, **kwargs):
            captured["memory_service_kwargs"] = kwargs

        def backfill_from_legacy(self):
            captured["backfill_called"] = True

        def close(self):
            pass

        def run_maintenance(self):
            return {"expired_deleted": 0, "cap_deleted": 0}

    monkeypatch.setattr(daemon_module, "ensure_gateway_resources", lambda **_kwargs: [])
    monkeypatch.setattr(daemon_module, "SQLiteStore", _FakeStore)
    monkeypatch.setattr(daemon_module, "PolicyEngine", lambda _settings: object())
    monkeypatch.setattr(daemon_module, "IMessageIngress", _FakeIngress)
    monkeypatch.setattr(daemon_module, "IMessageEgress", lambda **_kwargs: object())
    monkeypatch.setattr(daemon_module, "RelayOrchestrator", _FakeOrchestrator)
    monkeypatch.setattr(daemon_module, "RunExecutor", _FakeRunExecutor)
    monkeypatch.setattr(daemon_module, "MemoryService", _FakeMemoryService)
    monkeypatch.setattr(daemon_module, "CodexCliConnector", lambda **_kwargs: SimpleNamespace(shutdown=lambda: None))

    office = tmp_path / "agent-office"
    office.mkdir()
    soul = office / "SOUL.md"
    soul.write_text("identity", encoding="utf-8")

    settings = RelaySettings(
        db_path=tmp_path / "relay.db",
        default_workspace=str(tmp_path),
        allowed_workspaces=[str(tmp_path)],
        soul_file=str(soul),
        enable_memory=True,
        enable_memory_v2=True,
        memory_v2_shadow_mode=False,
        memory_v2_migrate_on_start=True,
    )

    daemon = RelayDaemon(settings)
    assert daemon.memory_service is not None
    assert captured.get("backfill_called") is True
    assert captured.get("orchestrator_memory_service") is daemon.memory_service

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
async def test_mail_poll_loop_skips_reprocessing_inflight_email():
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon._shutdown_requested = False
    daemon.settings = SimpleNamespace(mail_allowed_senders=[], poll_interval_seconds=0)
    daemon._concurrency_sem = asyncio.Semaphore(2)
    daemon._mail_owner = ""

    inbound = InboundMessage(
        id="mail_55",
        sender="user@example.com",
        text="relay: hello",
        received_at="2026-01-01T00:00:00Z",
        is_from_me=False,
    )

    fetch_calls = 0

    def _fetch_new(**kwargs):
        nonlocal fetch_calls
        fetch_calls += 1
        if fetch_calls >= 2:
            daemon._shutdown_requested = True
        return [inbound]

    daemon.mail_ingress = SimpleNamespace(fetch_new=_fetch_new)
    daemon.mail_egress = SimpleNamespace(was_recent_outbound=lambda sender, text: False)
    daemon.egress = SimpleNamespace(send=lambda *args, **kwargs: None)

    handled = 0

    class _FakeMailOrchestrator:
        def handle_message(self, msg):
            nonlocal handled
            handled += 1
            import time

            time.sleep(0.05)
            return SimpleNamespace(kind=CommandKind.CHAT, response="", run_id=None)

    daemon.mail_orchestrator = _FakeMailOrchestrator()

    await daemon._poll_mail_loop()
    assert handled == 1


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
    daemon.store = SimpleNamespace(
        set_state=lambda key, value: None,
        get_state=lambda key: None,
    )
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


@pytest.mark.asyncio
async def test_status_command_fastlane_bypasses_busy_concurrency_semaphore(tmp_path):
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon._shutdown_requested = False
    daemon._concurrency_sem = asyncio.Semaphore(1)
    await daemon._concurrency_sem.acquire()  # Simulate a long task occupying the worker slot.
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
                id="2",
                sender="+15551234567",
                text="status",
                received_at="2026-02-17T12:00:01Z",
                is_from_me=False,
            )
        ]
    )
    daemon.policy = SimpleNamespace(
        is_sender_allowed=lambda sender: True,
        is_under_rate_limit=lambda sender, now: True,
    )
    daemon.store = SimpleNamespace(
        set_state=lambda key, value: None,
        get_state=lambda key: None,
    )
    sent: list[tuple[str, str]] = []
    daemon.egress = SimpleNamespace(
        was_recent_outbound=lambda sender, text: False,
        send=lambda recipient, text: sent.append((recipient, text)),
    )

    class _StatusOrchestrator:
        def handle_message(self, msg):
            daemon._shutdown_requested = True
            daemon.egress.send(msg.sender, "No pending approvals.")
            return SimpleNamespace(kind=CommandKind.STATUS, response="No pending approvals.", run_id=None)

    daemon.orchestrator = _StatusOrchestrator()

    await asyncio.wait_for(daemon._poll_imessage_loop(), timeout=0.5)
    assert any("No pending approvals." in body for _, body in sent)


def test_consume_restart_echo_suppress_matches_and_clears():
    daemon = RelayDaemon.__new__(RelayDaemon)
    marker_store = {
        "value": (
            '{"sender":"+15551234567","text":"Apple Flow restarting... (text \\"health\\" to confirm it\'s back)",'
            '"expires_at":9999999999}'
        ),
        "clears": 0,
    }

    def _get_state(_key):
        return marker_store["value"]

    def _set_state(_key, value):
        marker_store["value"] = value
        marker_store["clears"] += 1

    daemon.store = SimpleNamespace(get_state=_get_state, set_state=_set_state)

    assert daemon._consume_restart_echo_suppress(
        "+15551234567",
        "Apple Flow restarting... (text 'health' to confirm it's back)",
    )
    assert marker_store["clears"] == 1
    assert marker_store["value"] == ""


def test_consume_restart_echo_suppress_ignores_non_matching_text():
    daemon = RelayDaemon.__new__(RelayDaemon)
    marker_store = {
        "value": (
            '{"sender":"+15551234567","text":"Apple Flow restarting... (text \\"health\\" to confirm it\'s back)",'
            '"expires_at":9999999999}'
        ),
        "clears": 0,
    }

    def _set_state(_key, value):
        marker_store["value"] = value
        marker_store["clears"] += 1

    daemon.store = SimpleNamespace(
        get_state=lambda _key: marker_store["value"],
        set_state=_set_state,
    )

    assert not daemon._consume_restart_echo_suppress("+15551234567", "hello there")
    assert marker_store["clears"] == 0


@pytest.mark.asyncio
async def test_run_executor_loop_cancelled_is_not_logged_as_error(caplog):
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon.run_executor = SimpleNamespace(
        run_forever=lambda _is_shutdown: (_ for _ in ()).throw(asyncio.CancelledError())
    )
    daemon._shutdown_requested = True

    caplog.set_level("INFO")
    await daemon._run_executor_loop()

    assert "Run executor loop cancelled during shutdown" in caplog.text
    assert "Run executor loop error" not in caplog.text


@pytest.mark.asyncio
async def test_run_forever_shutdown_does_not_raise_cancellederror():
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon._inflight_dispatch_tasks = set()
    daemon._shutdown_requested = False
    daemon.mail_ingress = None
    daemon.reminders_ingress = None
    daemon.notes_ingress = None
    daemon.calendar_ingress = None
    daemon.companion = None
    daemon.ambient = None

    async def _loop():
        await asyncio.sleep(60)

    daemon._poll_imessage_loop = _loop
    daemon._run_executor_loop = _loop

    task = asyncio.create_task(daemon.run_forever())
    await asyncio.sleep(0)
    task.cancel()
    await task

    assert task.done()
    assert not task.cancelled()


@pytest.mark.asyncio
async def test_top_level_run_handles_cancellederror_gracefully(monkeypatch):
    shutdown_called = {"value": False}

    class _FakeDaemon:
        def __init__(self, _settings):
            self.settings = _settings

        async def run_forever(self):
            raise asyncio.CancelledError()

        def shutdown(self):
            shutdown_called["value"] = True

        def request_shutdown(self):
            pass

        def send_startup_intro(self):
            pass

    settings = SimpleNamespace(
        allowed_senders=[],
        only_poll_allowed_senders=True,
        enable_mail_polling=False,
        enable_reminders_polling=False,
        enable_notes_polling=False,
        enable_calendar_polling=False,
        enable_companion=False,
        send_startup_intro=False,
    )

    monkeypatch.setattr(daemon_module, "RelaySettings", lambda: settings)
    monkeypatch.setattr(daemon_module, "migrate_legacy_db_if_needed", lambda _settings: False)
    monkeypatch.setattr(daemon_module, "RelayDaemon", _FakeDaemon)

    await daemon_module.run()
    assert shutdown_called["value"] is True
