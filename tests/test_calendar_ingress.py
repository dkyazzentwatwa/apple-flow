"""Tests for Apple Calendar ingress."""

import json
from unittest.mock import patch, MagicMock

from apple_flow.calendar_ingress import AppleCalendarIngress

from conftest import FakeStore


def _make_ingress(store=None, auto_approve=False):
    return AppleCalendarIngress(
        calendar_name="Codex Schedule",
        owner_sender="+15551234567",
        auto_approve=auto_approve,
        lookahead_minutes=5,
        store=store,
    )


def _mock_applescript_output(events):
    result = MagicMock()
    result.returncode = 0
    result.stdout = json.dumps(events)
    result.stderr = ""
    return result


# --- Fetch Tests ---


@patch("apple_flow.calendar_ingress.subprocess.run")
def test_fetch_new_returns_messages(mock_run):
    events = [
        {"id": "evt1", "summary": "Deploy staging", "description": "Push latest code", "start_date": "2026-02-17T10:00:00Z"},
        {"id": "evt2", "summary": "Run tests", "description": "", "start_date": "2026-02-17T10:05:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(events)

    ingress = _make_ingress()
    messages = ingress.fetch_new()

    assert len(messages) == 2
    assert messages[0].sender == "+15551234567"
    assert "Deploy staging" in messages[0].text
    assert messages[0].context["channel"] == "calendar"
    assert messages[0].context["event_id"] == "evt1"


@patch("apple_flow.calendar_ingress.subprocess.run")
def test_fetch_skips_processed_ids(mock_run):
    events = [
        {"id": "evt1", "summary": "Deploy", "description": "", "start_date": "2026-02-17T10:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(events)

    ingress = _make_ingress()
    ingress._processed_ids.add("evt1")
    messages = ingress.fetch_new()

    assert len(messages) == 0


@patch("apple_flow.calendar_ingress.subprocess.run")
def test_fetch_adds_task_prefix_by_default(mock_run):
    events = [
        {"id": "evt1", "summary": "Deploy", "description": "Details", "start_date": "2026-02-17T10:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(events)

    ingress = _make_ingress(auto_approve=False)
    messages = ingress.fetch_new()

    assert messages[0].text.startswith("task:")


@patch("apple_flow.calendar_ingress.subprocess.run")
def test_fetch_adds_relay_prefix_when_auto_approve(mock_run):
    events = [
        {"id": "evt1", "summary": "Deploy", "description": "Details", "start_date": "2026-02-17T10:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(events)

    ingress = _make_ingress(auto_approve=True)
    messages = ingress.fetch_new()

    assert messages[0].text.startswith("relay:")


@patch("apple_flow.calendar_ingress.subprocess.run")
def test_fetch_skips_empty_events(mock_run):
    events = [
        {"id": "evt1", "summary": "", "description": "", "start_date": "2026-02-17T10:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(events)

    ingress = _make_ingress()
    messages = ingress.fetch_new()

    assert len(messages) == 0


# --- Mark Processed ---


def test_mark_processed_persists_to_store():
    store = FakeStore()
    ingress = _make_ingress(store=store)

    ingress.mark_processed("evt123")

    assert "evt123" in ingress._processed_ids
    raw = store.get_state("calendar_processed_ids")
    assert raw is not None
    assert "evt123" in json.loads(raw)


def test_processed_ids_loaded_from_store():
    store = FakeStore()
    store.set_state("calendar_processed_ids", json.dumps(["evt1", "evt2"]))

    ingress = _make_ingress(store=store)

    assert "evt1" in ingress._processed_ids
    assert "evt2" in ingress._processed_ids


# --- Error Handling ---


@patch("apple_flow.calendar_ingress.subprocess.run")
def test_fetch_handles_applescript_error(mock_run):
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    result.stderr = "error"
    mock_run.return_value = result

    ingress = _make_ingress()
    assert ingress.fetch_new() == []


@patch("apple_flow.calendar_ingress.subprocess.run")
def test_fetch_handles_timeout(mock_run):
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=30)

    ingress = _make_ingress()
    assert ingress.fetch_new() == []


# --- Compose Text ---


def test_compose_text_summary_and_description():
    assert AppleCalendarIngress._compose_text("Summary", "Description") == "Summary\n\nDescription"


def test_compose_text_summary_only():
    assert AppleCalendarIngress._compose_text("Summary", "") == "Summary"


def test_compose_text_both_empty():
    assert AppleCalendarIngress._compose_text("", "") == ""
