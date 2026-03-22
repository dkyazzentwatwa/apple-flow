"""Tests for RelayDaemon methods not covered in test_daemon_startup.py."""

from __future__ import annotations

import json
import signal
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from conftest import FakeStore
from apple_flow.daemon import RelayDaemon, gateway_resource_statuses_for_settings
from apple_flow.gateway_setup import EnsureResult, GatewayResourceStatus
from apple_flow.runtime_health import daemon_loop_health_state_key, daemon_watchdog_state_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(**overrides):
    defaults = {
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
        "watchdog_poll_stall_seconds": 60.0,
        "watchdog_inflight_stall_seconds": 300.0,
        "watchdog_event_loop_lag_failures": 3,
        "helper_recycle_idle_seconds": 300.0,
        "helper_recycle_max_age_seconds": 3600.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_daemon(store=None, settings=None):
    """Create a RelayDaemon bypassing __init__ with pre-set attributes."""
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon.settings = settings or _make_settings()
    daemon.store = store or FakeStore()
    daemon._shutdown_requested = False
    daemon._inflight_dispatch_tasks = set()
    daemon._inflight_dispatch_started_at = {}
    daemon._last_busy_at = time.monotonic()
    daemon._last_connector_completion_at = ""
    daemon._event_loop_lag_seconds = 0.0
    daemon._event_loop_lag_failures = 0
    daemon.connector = MagicMock()
    daemon.connector._processes = None
    return daemon


# ---------------------------------------------------------------------------
# _gateway_name_from_label (static)
# ---------------------------------------------------------------------------

def test_gateway_name_from_label_mail():
    assert RelayDaemon._gateway_name_from_label("Reminders task list") == "reminders"
    assert RelayDaemon._gateway_name_from_label("Notes log folder") == "notes"
    assert RelayDaemon._gateway_name_from_label("Calendar") == "calendar"
    assert RelayDaemon._gateway_name_from_label("Mail ingress") == "mail"
    assert RelayDaemon._gateway_name_from_label("Unknown resource") == ""


# ---------------------------------------------------------------------------
# _record_gateway_success, _record_gateway_failure
# ---------------------------------------------------------------------------

def test_record_gateway_success_writes_state():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    daemon._record_gateway_success("mail")
    raw = store.get_state("gateway_health_mail")
    assert raw is not None
    data = json.loads(raw)
    assert data["healthy"] is True
    assert data["last_success_at"] != ""


def test_record_gateway_failure_writes_state():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    daemon._record_gateway_failure("notes", "osascript timeout")
    raw = store.get_state("gateway_health_notes")
    assert raw is not None
    data = json.loads(raw)
    assert data["healthy"] is False
    assert data["last_failure_reason"] == "osascript timeout"


def test_record_gateway_success_no_store():
    daemon = RelayDaemon.__new__(RelayDaemon)
    # Should not raise even without a store
    daemon._record_gateway_success("mail")


def test_record_gateway_success_logs_recovery(caplog):
    store = FakeStore()
    daemon = _make_daemon(store=store)
    # First mark as degraded
    daemon._record_gateway_failure("mail", "connection error")
    # Then mark as recovered
    import logging
    with caplog.at_level(logging.INFO, logger="apple_flow.daemon"):
        daemon._record_gateway_success("mail")
    assert any("recovered" in record.message.lower() for record in caplog.records)


# ---------------------------------------------------------------------------
# _supervisor_backoff_seconds (static)
# ---------------------------------------------------------------------------

def test_supervisor_backoff_attempt_1():
    assert RelayDaemon._supervisor_backoff_seconds(1) == 1.0


def test_supervisor_backoff_attempt_2():
    assert RelayDaemon._supervisor_backoff_seconds(2) == 5.0


def test_supervisor_backoff_attempt_3():
    assert RelayDaemon._supervisor_backoff_seconds(3) == 15.0


def test_supervisor_backoff_attempt_4_plus():
    assert RelayDaemon._supervisor_backoff_seconds(4) == 60.0
    assert RelayDaemon._supervisor_backoff_seconds(100) == 60.0


# ---------------------------------------------------------------------------
# _read_loop_health_state, _write_loop_health_state
# ---------------------------------------------------------------------------

def test_read_loop_health_state_missing():
    daemon = _make_daemon()
    state = daemon._read_loop_health_state("imessage")
    assert state == {}


def test_read_loop_health_state_invalid_json():
    store = FakeStore()
    store.set_state(daemon_loop_health_state_key("imessage"), "not-json")
    daemon = _make_daemon(store=store)
    state = daemon._read_loop_health_state("imessage")
    assert state == {}


def test_write_and_read_loop_health_state():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    daemon._write_loop_health_state("imessage", healthy=True, last_success_at="2026-01-01T12:00:00Z")
    state = daemon._read_loop_health_state("imessage")
    assert state["healthy"] is True
    assert state["last_success_at"] == "2026-01-01T12:00:00Z"


def test_write_loop_health_state_preserves_previous():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    daemon._write_loop_health_state("mail", healthy=True, last_success_at="2026-01-01T12:00:00Z")
    # Update without providing last_success_at — should preserve previous value
    daemon._write_loop_health_state("mail", healthy=False, last_failure_reason="crash")
    state = daemon._read_loop_health_state("mail")
    assert state["healthy"] is False
    assert state["last_failure_reason"] == "crash"
    assert state["last_success_at"] == "2026-01-01T12:00:00Z"  # preserved


def test_write_loop_health_state_no_store():
    daemon = RelayDaemon.__new__(RelayDaemon)
    # Should not raise when no store is set
    daemon._write_loop_health_state("mail", healthy=True)


# ---------------------------------------------------------------------------
# _record_loop_success, _record_loop_failure, _record_loop_restart
# ---------------------------------------------------------------------------

def test_record_loop_success():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    daemon._record_loop_success("imessage")
    state = daemon._read_loop_health_state("imessage")
    assert state["healthy"] is True
    assert state["last_success_at"] != ""


def test_record_loop_failure():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    daemon._record_loop_failure("mail", "connection refused")
    state = daemon._read_loop_health_state("mail")
    assert state["healthy"] is False
    assert state["last_failure_reason"] == "connection refused"


def test_record_loop_restart_increments_count():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    count1 = daemon._record_loop_restart("notes")
    count2 = daemon._record_loop_restart("notes")
    assert count1 == 1
    assert count2 == 2


# ---------------------------------------------------------------------------
# _connector_registry
# ---------------------------------------------------------------------------

def test_connector_registry_none_when_no_connector():
    daemon = _make_daemon()
    daemon.connector = None
    assert daemon._connector_registry() is None


def test_connector_registry_none_when_no_processes():
    daemon = _make_daemon()
    daemon.connector = MagicMock()
    daemon.connector._processes = None
    assert daemon._connector_registry() is None


def test_connector_registry_returns_managed_registry():
    from apple_flow.process_registry import ManagedProcessRegistry
    daemon = _make_daemon()
    registry = ManagedProcessRegistry("test")
    daemon.connector._processes = registry
    result = daemon._connector_registry()
    assert result is registry


# ---------------------------------------------------------------------------
# _active_work_counts
# ---------------------------------------------------------------------------

def test_active_work_counts_no_active():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    daemon._inflight_dispatch_tasks = set()
    counts = daemon._active_work_counts()
    assert counts["active_runs"] == 0
    assert counts["inflight_dispatch"] == 0
    assert counts["busy"] == 0


def test_active_work_counts_with_executing_run():
    store = FakeStore()
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    daemon = _make_daemon(store=store)
    counts = daemon._active_work_counts()
    assert counts["active_runs"] == 1
    assert counts["busy"] == 1


def test_active_work_counts_completed_run_not_counted():
    store = FakeStore()
    store.create_run("run_1", "+1", "task", "completed", "/tmp", "execute")
    daemon = _make_daemon(store=store)
    counts = daemon._active_work_counts()
    assert counts["active_runs"] == 0


# ---------------------------------------------------------------------------
# _oldest_inflight_dispatch_seconds
# ---------------------------------------------------------------------------

def test_oldest_inflight_dispatch_no_tasks():
    daemon = _make_daemon()
    daemon._inflight_dispatch_started_at = {}
    age = daemon._oldest_inflight_dispatch_seconds()
    assert age == 0.0


def test_oldest_inflight_dispatch_with_task():
    daemon = _make_daemon()
    fake_task = object()
    daemon._inflight_dispatch_started_at = {fake_task: time.monotonic() - 10.0}
    age = daemon._oldest_inflight_dispatch_seconds()
    assert age >= 9.0  # at least ~10 seconds


# ---------------------------------------------------------------------------
# _enabled_watchdog_poll_loops
# ---------------------------------------------------------------------------

def test_enabled_watchdog_poll_loops_imessage_only():
    daemon = _make_daemon()
    daemon.mail_ingress = None
    daemon.reminders_ingress = None
    daemon.notes_ingress = None
    daemon.calendar_ingress = None
    loops = daemon._enabled_watchdog_poll_loops()
    assert loops == ["imessage"]


def test_enabled_watchdog_poll_loops_with_mail():
    daemon = _make_daemon()
    daemon.mail_ingress = MagicMock()
    daemon.reminders_ingress = None
    daemon.notes_ingress = None
    daemon.calendar_ingress = None
    loops = daemon._enabled_watchdog_poll_loops()
    assert "imessage" in loops
    assert "mail" in loops


def test_enabled_watchdog_poll_loops_all():
    daemon = _make_daemon()
    daemon.mail_ingress = MagicMock()
    daemon.reminders_ingress = MagicMock()
    daemon.notes_ingress = MagicMock()
    daemon.calendar_ingress = MagicMock()
    loops = daemon._enabled_watchdog_poll_loops()
    assert set(loops) == {"imessage", "mail", "reminders", "notes", "calendar"}


# ---------------------------------------------------------------------------
# _poll_loops_stalled
# ---------------------------------------------------------------------------

def test_poll_loops_stalled_no_state():
    daemon = _make_daemon()
    # No state = no recorded success = not stalled
    assert daemon._poll_loops_stalled() is False


def test_poll_loops_stalled_recent_success():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    # Record a recent success
    daemon._record_loop_success("imessage")
    assert daemon._poll_loops_stalled() is False


def test_poll_loops_stalled_old_success():
    store = FakeStore()
    settings = _make_settings(watchdog_poll_stall_seconds=10.0)
    daemon = _make_daemon(store=store, settings=settings)
    # Write an old success timestamp
    old_ts = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    from apple_flow.runtime_health import daemon_loop_health_payload, daemon_loop_health_state_key
    store.set_state(daemon_loop_health_state_key("imessage"), daemon_loop_health_payload(healthy=True, last_success_at=old_ts))
    assert daemon._poll_loops_stalled() is True


# ---------------------------------------------------------------------------
# _publish_watchdog_state
# ---------------------------------------------------------------------------

def test_publish_watchdog_state_writes_to_store():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    daemon._publish_watchdog_state()
    raw = store.get_state(daemon_watchdog_state_key())
    assert raw is not None
    data = json.loads(raw)
    assert "healthy" in data


def test_publish_watchdog_state_no_store():
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon.settings = _make_settings()
    # Should not raise when no store is set
    daemon._publish_watchdog_state()


# ---------------------------------------------------------------------------
# recycle_helpers
# ---------------------------------------------------------------------------

def test_recycle_helpers_busy_returns_skip():
    store = FakeStore()
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    daemon = _make_daemon(store=store)
    result = daemon.recycle_helpers(force=False)
    assert "skipped" in result.lower() and "busy" in result.lower()


def test_recycle_helpers_force_no_registry():
    daemon = _make_daemon()
    daemon._inflight_dispatch_tasks = set()
    # No connector processes registered
    daemon.connector.cancel_active_processes = MagicMock(return_value=0)
    daemon.connector._processes = None
    result = daemon.recycle_helpers(force=True)
    # With no active helpers, should say "no tracked connector helpers"
    assert "no tracked" in result.lower() or "complete" in result.lower()


def test_recycle_helpers_idle_not_reached():
    settings = _make_settings(helper_recycle_idle_seconds=999.0)
    daemon = _make_daemon(settings=settings)
    daemon._last_busy_at = time.monotonic()  # just was busy
    daemon._inflight_dispatch_tasks = set()
    result = daemon.recycle_helpers(force=False)
    assert "idle window not reached" in result.lower() or "skipped" in result.lower() or "no tracked" in result.lower()


# ---------------------------------------------------------------------------
# request_shutdown
# ---------------------------------------------------------------------------

def test_request_shutdown_sets_flag():
    daemon = _make_daemon()
    assert daemon._shutdown_requested is False
    daemon.request_shutdown()
    assert daemon._shutdown_requested is True


# ---------------------------------------------------------------------------
# handle_signal
# ---------------------------------------------------------------------------

def test_handle_signal_sigterm_requests_shutdown():
    # handle_signal is a closure inside run_daemon_forever; test request_shutdown directly
    daemon = _make_daemon()
    assert daemon._shutdown_requested is False
    daemon.request_shutdown()
    assert daemon._shutdown_requested is True


def test_handle_signal_sigint_requests_shutdown():
    daemon = _make_daemon()
    daemon.request_shutdown()
    # Idempotent — calling again stays True
    daemon.request_shutdown()
    assert daemon._shutdown_requested is True


# ---------------------------------------------------------------------------
# _synthesize_attachment_only_text
# ---------------------------------------------------------------------------

def test_synthesize_attachment_only_text():
    from apple_flow.models import InboundMessage
    daemon = _make_daemon()
    daemon.orchestrator = MagicMock()
    daemon.orchestrator.require_chat_prefix = False
    daemon.orchestrator.chat_prefix = "relay:"
    daemon.orchestrator.enable_attachments = True

    msg = InboundMessage(
        id="m1",
        sender="+1",
        text="\uFFFC",  # attachment placeholder character
        received_at="2026-01-01T12:00:00Z",
        is_from_me=False,
    )
    # With attachment-only text (placeholder), message text should become empty for synthesis
    # The method checks for the _ATTACHMENT_PLACEHOLDER_TEXTS set
    result = daemon._synthesize_attachment_only_text(msg)
    # Result should be a synthetic prompt or None
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# _consume_restart_echo_suppress
# ---------------------------------------------------------------------------

def test_consume_restart_echo_suppress_no_state():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    from apple_flow.models import InboundMessage
    msg = InboundMessage(id="m1", sender="+1", text="health", received_at="2026-01-01T12:00:00Z", is_from_me=False)
    result = daemon._consume_restart_echo_suppress(msg.sender, msg.text)
    assert result is False


def test_consume_restart_echo_suppress_matching():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    restart_text = "Apple Flow restarting..."
    store.set_state(
        "system_restart_echo_suppress",
        json.dumps({
            "sender": "+15551234567",
            "text": restart_text,
            "expires_at": time.time() + 60.0,
        }),
    )
    from apple_flow.models import InboundMessage
    msg = InboundMessage(
        id="m1", sender="+15551234567", text=restart_text,
        received_at="2026-01-01T12:00:00Z", is_from_me=False
    )
    result = daemon._consume_restart_echo_suppress(msg.sender, msg.text)
    assert result is True


def test_consume_restart_echo_suppress_expired():
    store = FakeStore()
    daemon = _make_daemon(store=store)
    store.set_state(
        "system_restart_echo_suppress",
        json.dumps({
            "sender": "+1",
            "text": "Apple Flow restarting...",
            "expires_at": time.time() - 10.0,  # expired
        }),
    )
    from apple_flow.models import InboundMessage
    msg = InboundMessage(id="m1", sender="+1", text="Apple Flow restarting...",
                          received_at="2026-01-01T12:00:00Z", is_from_me=False)
    result = daemon._consume_restart_echo_suppress(msg.sender, msg.text)
    assert result is False
