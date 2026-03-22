"""Tests for runtime_health module."""

from __future__ import annotations

import json

from apple_flow.runtime_health import (
    KNOWN_DAEMON_LOOPS,
    daemon_loop_health_payload,
    daemon_loop_health_state_key,
    daemon_watchdog_payload,
    daemon_watchdog_state_key,
    read_all_daemon_loop_health,
    read_daemon_loop_health,
    read_daemon_watchdog,
    summarize_runtime_health_lines,
)


class FakeStore:
    def __init__(self, state: dict[str, str] | None = None):
        self._state = state or {}

    def get_state(self, key: str) -> str | None:
        return self._state.get(key)


class StoreWithoutGetState:
    pass


# --- daemon_loop_health_state_key ---

def test_loop_state_key_format():
    assert daemon_loop_health_state_key("imessage") == "daemon_loop_health_imessage"
    assert daemon_loop_health_state_key("mail") == "daemon_loop_health_mail"


# --- daemon_watchdog_state_key ---

def test_watchdog_state_key():
    assert daemon_watchdog_state_key() == "daemon_watchdog"


# --- daemon_loop_health_payload ---

def test_loop_health_payload_healthy():
    raw = daemon_loop_health_payload(healthy=True, last_success_at="2026-01-01T00:00:00+00:00")
    data = json.loads(raw)
    assert data["healthy"] is True
    assert data["last_success_at"] == "2026-01-01T00:00:00+00:00"
    assert data["restart_count"] == 0
    assert data["last_restart_at"] == ""


def test_loop_health_payload_degraded_with_restart():
    raw = daemon_loop_health_payload(
        healthy=False,
        last_failure_reason="exception",
        restart_count=3,
        last_restart_at="2026-01-01T01:00:00+00:00",
    )
    data = json.loads(raw)
    assert data["healthy"] is False
    assert data["restart_count"] == 3
    assert data["last_failure_reason"] == "exception"


def test_loop_health_payload_defaults():
    raw = daemon_loop_health_payload(healthy=True)
    data = json.loads(raw)
    assert data["last_success_at"] == ""
    assert data["last_failure_at"] == ""
    assert data["last_failure_reason"] == ""
    assert data["restart_count"] == 0
    assert data["last_restart_at"] == ""


# --- daemon_watchdog_payload ---

def test_watchdog_payload_healthy():
    raw = daemon_watchdog_payload(healthy=True)
    data = json.loads(raw)
    assert data["healthy"] is True
    assert data["degraded_reasons"] == []
    assert data["oldest_inflight_dispatch_seconds"] == 0.0


def test_watchdog_payload_degraded_with_reasons():
    raw = daemon_watchdog_payload(
        healthy=False,
        degraded_reasons=["poll_stalled", "event_loop_lag"],
        active_helper_count=2,
        event_loop_lag_seconds=1.5,
        event_loop_lag_failures=3,
    )
    data = json.loads(raw)
    assert data["healthy"] is False
    assert data["degraded_reasons"] == ["poll_stalled", "event_loop_lag"]
    assert data["active_helper_count"] == 2
    assert data["event_loop_lag_seconds"] == 1.5
    assert data["event_loop_lag_failures"] == 3


def test_watchdog_payload_none_reasons():
    raw = daemon_watchdog_payload(healthy=True, degraded_reasons=None)
    data = json.loads(raw)
    assert data["degraded_reasons"] == []


# --- read_daemon_loop_health ---

def test_read_loop_health_found():
    key = daemon_loop_health_state_key("imessage")
    payload = daemon_loop_health_payload(healthy=True)
    store = FakeStore({key: payload})
    result = read_daemon_loop_health(store, "imessage")
    assert result is not None
    assert result["healthy"] is True


def test_read_loop_health_missing():
    store = FakeStore()
    result = read_daemon_loop_health(store, "imessage")
    assert result is None


def test_read_loop_health_malformed_json():
    key = daemon_loop_health_state_key("imessage")
    store = FakeStore({key: "bad-json"})
    result = read_daemon_loop_health(store, "imessage")
    assert result is None


def test_read_loop_health_non_dict_json():
    key = daemon_loop_health_state_key("imessage")
    store = FakeStore({key: json.dumps([1, 2])})
    result = read_daemon_loop_health(store, "imessage")
    assert result is None


def test_read_loop_health_store_without_get_state():
    store = StoreWithoutGetState()
    result = read_daemon_loop_health(store, "imessage")  # type: ignore[arg-type]
    assert result is None


# --- read_all_daemon_loop_health ---

def test_read_all_loop_health_multiple():
    state = {
        daemon_loop_health_state_key("imessage"): daemon_loop_health_payload(healthy=True),
        daemon_loop_health_state_key("mail"): daemon_loop_health_payload(healthy=False),
    }
    store = FakeStore(state)
    result = read_all_daemon_loop_health(store)
    assert "imessage" in result
    assert "mail" in result
    assert "calendar" not in result


def test_read_all_loop_health_empty():
    store = FakeStore()
    result = read_all_daemon_loop_health(store)
    assert result == {}


def test_read_all_loop_health_all_known():
    state = {
        daemon_loop_health_state_key(name): daemon_loop_health_payload(healthy=True)
        for name in KNOWN_DAEMON_LOOPS
    }
    store = FakeStore(state)
    result = read_all_daemon_loop_health(store)
    assert set(result.keys()) == set(KNOWN_DAEMON_LOOPS)


# --- read_daemon_watchdog ---

def test_read_daemon_watchdog_found():
    payload = daemon_watchdog_payload(healthy=True, active_helper_count=1)
    store = FakeStore({daemon_watchdog_state_key(): payload})
    result = read_daemon_watchdog(store)
    assert result is not None
    assert result["healthy"] is True
    assert result["active_helper_count"] == 1


def test_read_daemon_watchdog_missing():
    store = FakeStore()
    result = read_daemon_watchdog(store)
    assert result is None


def test_read_daemon_watchdog_malformed():
    store = FakeStore({daemon_watchdog_state_key(): "not-json"})
    result = read_daemon_watchdog(store)
    assert result is None


# --- summarize_runtime_health_lines ---

def test_summarize_healthy_watchdog_and_loop():
    watchdog = daemon_watchdog_payload(
        healthy=True,
        oldest_inflight_dispatch_seconds=5.0,
        active_helper_count=2,
        event_loop_lag_seconds=0.01,
    )
    loop = daemon_loop_health_payload(healthy=True)
    store = FakeStore(
        {
            daemon_watchdog_state_key(): watchdog,
            daemon_loop_health_state_key("imessage"): loop,
        }
    )
    lines = summarize_runtime_health_lines(store)
    # Should have watchdog line + loop line
    assert len(lines) == 2
    assert any("Runtime: OK" in l for l in lines)
    assert any("Loop imessage: OK" in l for l in lines)


def test_summarize_degraded_watchdog():
    watchdog = daemon_watchdog_payload(
        healthy=False,
        degraded_reasons=["poll_stalled"],
    )
    store = FakeStore({daemon_watchdog_state_key(): watchdog})
    lines = summarize_runtime_health_lines(store)
    assert len(lines) == 1
    assert "Runtime: DEGRADED" in lines[0]
    assert "poll_stalled" in lines[0]


def test_summarize_loop_with_restarts():
    loop = daemon_loop_health_payload(healthy=False, restart_count=2, last_failure_reason="crash")
    store = FakeStore({daemon_loop_health_state_key("mail"): loop})
    lines = summarize_runtime_health_lines(store)
    assert len(lines) == 1
    assert "Loop mail: DEGRADED" in lines[0]
    assert "restarts 2" in lines[0]
    assert "crash" in lines[0]


def test_summarize_loop_healthy_with_restarts():
    # Healthy loop with restart_count should still show restarts
    loop = daemon_loop_health_payload(healthy=True, restart_count=1)
    store = FakeStore({daemon_loop_health_state_key("mail"): loop})
    lines = summarize_runtime_health_lines(store)
    assert "restarts 1" in lines[0]


def test_summarize_empty_store():
    store = FakeStore()
    lines = summarize_runtime_health_lines(store)
    assert lines == []


def test_summarize_watchdog_with_inflight_and_helpers():
    watchdog = daemon_watchdog_payload(
        healthy=True,
        oldest_inflight_dispatch_seconds=30.0,
        active_helper_count=3,
        event_loop_lag_seconds=0.05,
    )
    store = FakeStore({daemon_watchdog_state_key(): watchdog})
    lines = summarize_runtime_health_lines(store)
    assert len(lines) == 1
    assert "inflight 30s" in lines[0]
    assert "helpers 3" in lines[0]
    assert "loop lag 0.05s" in lines[0]


def test_summarize_watchdog_no_degraded_reasons_shown_when_healthy():
    watchdog = daemon_watchdog_payload(healthy=True, degraded_reasons=[])
    store = FakeStore({daemon_watchdog_state_key(): watchdog})
    lines = summarize_runtime_health_lines(store)
    assert lines[0].startswith("Runtime: OK")
    assert "DEGRADED" not in lines[0]
    # Between "Runtime: OK" and "inflight" only the separator appears (no reason text)
    between = lines[0].split("Runtime: OK")[1].split("inflight")[0]
    assert between.strip() == "|"
