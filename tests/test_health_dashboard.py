"""Tests for health dashboard command."""

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.commanding import CommandKind
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


def _make_orchestrator(store=None):
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=store or FakeStore(),
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
    )


def test_health_command_returns_stats():
    store = FakeStore()
    store.sessions["user1"] = {"thread_id": "t1", "mode": "chat"}
    store.sessions["user2"] = {"thread_id": "t2", "mode": "idea"}
    orch = _make_orchestrator(store=store)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="health",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.HEALTH
    assert "Apple Flow Health" in result.response
    assert "Sessions: 2" in result.response


def test_health_shows_pending_approvals():
    store = FakeStore()
    store.approvals["req1"] = {
        "request_id": "req1", "run_id": "r1", "sender": "+1",
        "summary": "test", "command_preview": "test",
        "expires_at": "2030-01-01T00:00:00Z", "status": "pending",
    }
    orch = _make_orchestrator(store=store)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="health",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert "Pending approvals: 1" in result.response


def test_health_shows_uptime_when_started_at_stored():
    store = FakeStore()
    store.state["daemon_started_at"] = "2026-02-17T10:00:00+00:00"
    orch = _make_orchestrator(store=store)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="health",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert "Uptime:" in result.response


def test_health_sends_response_to_sender():
    orch = _make_orchestrator()

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="health",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    orch.handle_message(msg)
    assert any("+15551234567" in recipient for recipient, _ in orch.egress.messages)


def test_health_shows_companion_status():
    """When companion kv_state keys are present, health response includes Companion line."""
    from datetime import datetime, timedelta

    store = FakeStore()
    # Simulate a companion check 5 minutes ago with no observations
    check_time = (datetime.now() - timedelta(minutes=5)).isoformat()
    store.set_state("companion_last_check_at", check_time)
    store.set_state("companion_last_obs_count", "0")
    store.set_state("companion_last_skip_reason", "no_observations")
    store.set_state("companion_proactive_hour_count", "1")
    orch = _make_orchestrator(store=store)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="health",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert "Companion:" in result.response
    assert "no_observations" in result.response
    assert "1/hr sent" in result.response


def test_health_no_companion_data():
    """When no companion kv_state keys exist, health response has no Companion line."""
    store = FakeStore()
    orch = _make_orchestrator(store=store)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="health",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert "Companion:" not in result.response


def test_health_companion_muted_flag():
    """Muted companion shows MUTED in health output."""
    from datetime import datetime, timedelta

    store = FakeStore()
    check_time = (datetime.now() - timedelta(minutes=2)).isoformat()
    store.set_state("companion_last_check_at", check_time)
    store.set_state("companion_last_obs_count", "0")
    store.set_state("companion_last_skip_reason", "muted")
    store.set_state("companion_muted", "true")
    orch = _make_orchestrator(store=store)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="health",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert "MUTED" in result.response


def test_health_shows_gateway_degradation():
    store = FakeStore()
    store.set_state(
        "gateway_health_notes",
        '{"healthy": false, "last_failure_reason": "Connection invalid", "last_failure_at": "2026-03-10T12:00:00+00:00"}',
    )
    store.set_state(
        "gateway_health_reminders",
        '{"healthy": true, "last_success_at": "2026-03-10T12:05:00+00:00"}',
    )
    orch = _make_orchestrator(store=store)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="health",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)

    assert "Gateways:" in result.response
    assert "Notes: DEGRADED" in result.response
    assert "Connection invalid" in result.response
    assert "Reminders: OK" in result.response


def test_health_shows_runtime_watchdog_and_loop_status():
    store = FakeStore()
    store.set_state(
        "daemon_loop_health_imessage",
        '{"healthy": true, "last_success_at": "2026-03-11T12:05:00+00:00", "restart_count": 2}',
    )
    store.set_state(
        "daemon_watchdog",
        (
            '{"healthy": false, "degraded_reasons": ["poll_stalled", "event_loop_lag"], '
            '"oldest_inflight_dispatch_seconds": 301.0, "active_helper_count": 1, '
            '"oldest_helper_age_seconds": 4200.0, "event_loop_lag_seconds": 5.4}'
        ),
    )
    orch = _make_orchestrator(store=store)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="health",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)

    assert "Runtime:" in result.response
    assert "DEGRADED" in result.response
    assert "poll_stalled" in result.response
    assert "Loop imessage: OK" in result.response
