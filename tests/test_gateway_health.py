"""Tests for gateway_health module."""

from __future__ import annotations

import json

import pytest

from apple_flow.gateway_health import (
    KNOWN_GATEWAYS,
    gateway_health_payload,
    gateway_health_state_key,
    now_utc_iso,
    read_all_gateway_health,
    read_gateway_health,
    summarize_gateway_health_lines,
)


class FakeStore:
    def __init__(self, state: dict[str, str] | None = None):
        self._state = state or {}

    def get_state(self, key: str) -> str | None:
        return self._state.get(key)


class StoreWithoutGetState:
    pass


# --- gateway_health_state_key ---

def test_state_key_format():
    assert gateway_health_state_key("mail") == "gateway_health_mail"
    assert gateway_health_state_key("notes") == "gateway_health_notes"
    assert gateway_health_state_key("reminders") == "gateway_health_reminders"
    assert gateway_health_state_key("calendar") == "gateway_health_calendar"


# --- gateway_health_payload ---

def test_payload_healthy():
    raw = gateway_health_payload(healthy=True, last_success_at="2026-01-01T00:00:00+00:00")
    data = json.loads(raw)
    assert data["healthy"] is True
    assert data["last_success_at"] == "2026-01-01T00:00:00+00:00"
    assert data["last_failure_at"] == ""
    assert data["last_failure_reason"] == ""


def test_payload_degraded():
    raw = gateway_health_payload(
        healthy=False,
        last_failure_at="2026-01-02T00:00:00+00:00",
        last_failure_reason="osascript timeout",
    )
    data = json.loads(raw)
    assert data["healthy"] is False
    assert data["last_failure_reason"] == "osascript timeout"
    assert data["last_failure_at"] == "2026-01-02T00:00:00+00:00"


def test_payload_defaults():
    raw = gateway_health_payload(healthy=True)
    data = json.loads(raw)
    assert data["last_success_at"] == ""
    assert data["last_failure_at"] == ""
    assert data["last_failure_reason"] == ""


# --- read_gateway_health ---

def test_read_gateway_health_returns_dict():
    payload = gateway_health_payload(healthy=True, last_success_at="2026-01-01T00:00:00+00:00")
    store = FakeStore({"gateway_health_mail": payload})
    result = read_gateway_health(store, "mail")
    assert result is not None
    assert result["healthy"] is True


def test_read_gateway_health_missing_key():
    store = FakeStore()
    result = read_gateway_health(store, "mail")
    assert result is None


def test_read_gateway_health_malformed_json():
    store = FakeStore({"gateway_health_mail": "not-json"})
    result = read_gateway_health(store, "mail")
    assert result is None


def test_read_gateway_health_non_dict_json():
    store = FakeStore({"gateway_health_mail": json.dumps([1, 2, 3])})
    result = read_gateway_health(store, "mail")
    assert result is None


def test_read_gateway_health_store_without_get_state():
    store = StoreWithoutGetState()
    result = read_gateway_health(store, "mail")  # type: ignore[arg-type]
    assert result is None


# --- read_all_gateway_health ---

def test_read_all_gateway_health_multiple():
    mail_payload = gateway_health_payload(healthy=True)
    notes_payload = gateway_health_payload(healthy=False, last_failure_reason="err")
    store = FakeStore(
        {
            "gateway_health_mail": mail_payload,
            "gateway_health_notes": notes_payload,
        }
    )
    result = read_all_gateway_health(store)
    assert "mail" in result
    assert "notes" in result
    assert "reminders" not in result
    assert "calendar" not in result


def test_read_all_gateway_health_empty():
    store = FakeStore()
    result = read_all_gateway_health(store)
    assert result == {}


def test_read_all_gateway_health_all_known_gateways():
    state = {
        gateway_health_state_key(g): gateway_health_payload(healthy=True)
        for g in KNOWN_GATEWAYS
    }
    store = FakeStore(state)
    result = read_all_gateway_health(store)
    assert set(result.keys()) == set(KNOWN_GATEWAYS)


# --- summarize_gateway_health_lines ---

def test_summarize_healthy_gateway():
    payload = gateway_health_payload(healthy=True, last_success_at="2026-01-01T12:00:00+00:00")
    store = FakeStore({"gateway_health_mail": payload})
    lines = summarize_gateway_health_lines(store)
    assert len(lines) == 1
    assert lines[0].startswith("Mail: OK")
    assert "2026-01-01T12:00:00+00:00" in lines[0]


def test_summarize_healthy_gateway_no_timestamp():
    payload = gateway_health_payload(healthy=True)
    store = FakeStore({"gateway_health_mail": payload})
    lines = summarize_gateway_health_lines(store)
    assert lines[0] == "Mail: OK"


def test_summarize_degraded_gateway():
    payload = gateway_health_payload(
        healthy=False,
        last_failure_reason="osascript timeout",
        last_failure_at="2026-01-02T00:00:00+00:00",
    )
    store = FakeStore({"gateway_health_notes": payload})
    lines = summarize_gateway_health_lines(store)
    assert len(lines) == 1
    assert "Notes: DEGRADED" in lines[0]
    assert "osascript timeout" in lines[0]
    assert "2026-01-02T00:00:00+00:00" in lines[0]


def test_summarize_empty_store():
    store = FakeStore()
    lines = summarize_gateway_health_lines(store)
    assert lines == []


def test_summarize_multiple_gateways():
    store = FakeStore(
        {
            "gateway_health_mail": gateway_health_payload(healthy=True),
            "gateway_health_reminders": gateway_health_payload(healthy=False, last_failure_reason="err"),
        }
    )
    lines = summarize_gateway_health_lines(store)
    assert len(lines) == 2
    labels = [l.split(":")[0] for l in lines]
    assert "Mail" in labels
    assert "Reminders" in labels


# --- now_utc_iso ---

def test_now_utc_iso_format():
    ts = now_utc_iso()
    # Should be parseable as ISO
    from datetime import datetime
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
