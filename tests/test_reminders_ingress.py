"""Tests for Apple Reminders ingress module."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import FakeStore

from apple_flow.reminders_ingress import AppleRemindersIngress


def _due_in(offset_seconds: int) -> str:
    return (datetime.now() + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%d %H:%M:%S")


def test_fetch_new_converts_to_inbound_messages(monkeypatch):
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )
    raw = [
        {
            "id": "rem_001",
            "name": "Fix the login bug",
            "body": "Users can't log in with SSO",
            "creation_date": "2026-02-17T10:00:00",
            "due_date": "",
        },
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert len(messages) == 1
    msg = messages[0]
    assert msg.id == "reminder_rem_001"
    assert msg.sender == "+15551234567"
    assert "Fix the login bug" in msg.text
    assert "Users can't log in with SSO" in msg.text
    assert msg.text.startswith("task:")  # default: not auto-approve
    assert msg.is_from_me is False
    assert msg.context["channel"] == "reminders"
    assert msg.context["reminder_id"] == "rem_001"
    assert msg.context["occurrence_key"] == "rem_001|"


def test_fetch_new_auto_approve_uses_relay_prefix(monkeypatch):
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        auto_approve=True,
        store=store,
    )
    raw = [
        {"id": "rem_002", "name": "Explain the auth flow", "body": "", "creation_date": "", "due_date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert len(messages) == 1
    assert messages[0].text.startswith("relay:")


def test_fetch_new_skips_already_processed_occurrence(monkeypatch):
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )
    ingress.mark_processed_occurrence("rem_001|")

    raw = [
        {"id": "rem_001", "name": "Already done", "body": "", "creation_date": "", "due_date": ""},
        {"id": "rem_002", "name": "New task", "body": "", "creation_date": "", "due_date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert len(messages) == 1
    assert messages[0].id == "reminder_rem_002"


def test_fetch_new_skips_empty_names(monkeypatch):
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )
    raw = [
        {"id": "rem_empty", "name": "", "body": "", "creation_date": "", "due_date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert messages == []


def test_fetch_new_skips_missing_id(monkeypatch):
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )
    raw = [
        {"id": "", "name": "No ID", "body": "", "creation_date": "", "due_date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert messages == []


def test_mark_processed_occurrence_persists_to_store():
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )

    ingress.mark_processed_occurrence("rem_001|")
    ingress.mark_processed_occurrence("rem_002|2026-03-01 12:00:00")

    raw = store.get_state("reminders_processed_occurrences")
    assert raw is not None
    occurrences = json.loads(raw)
    assert "rem_001|" in occurrences
    assert "rem_002|2026-03-01 12:00:00" in occurrences


def test_processed_occurrences_hydrated_from_store():
    store = FakeStore()
    store.set_state(
        "reminders_processed_occurrences",
        json.dumps(["rem_old_1|", "rem_old_2|2026-03-01 08:00:00"]),
    )

    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )
    assert "rem_old_1|" in ingress._processed_occurrences
    assert "rem_old_2|2026-03-01 08:00:00" in ingress._processed_occurrences


def test_legacy_processed_ids_migrated_to_occurrences():
    store = FakeStore()
    store.set_state("reminders_processed_ids", json.dumps(["rem_old_1", "rem_old_2"]))

    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )
    assert "rem_old_1|" in ingress._processed_occurrences
    assert "rem_old_2|" in ingress._processed_occurrences
    migrated = store.get_state("reminders_processed_occurrences")
    assert migrated is not None
    assert "rem_old_1|" in json.loads(migrated)


def test_latest_rowid_returns_zero():
    ingress = AppleRemindersIngress()
    assert ingress.latest_rowid() == 0


def test_compose_text_name_only():
    result = AppleRemindersIngress._compose_text("Fix the bug", "", "")
    assert result == "Fix the bug"


def test_compose_text_name_and_body():
    result = AppleRemindersIngress._compose_text("Fix the bug", "Details here", "")
    assert "Fix the bug" in result
    assert "Details here" in result


def test_compose_text_name_and_due_date():
    result = AppleRemindersIngress._compose_text("Fix the bug", "", "2026-03-01")
    assert "Fix the bug" in result
    assert "2026-03-01" in result


def test_compose_text_all_fields():
    result = AppleRemindersIngress._compose_text("Fix the bug", "Details here", "2026-03-01")
    assert "Fix the bug" in result
    assert "Details here" in result
    assert "2026-03-01" in result


def test_compose_text_empty():
    result = AppleRemindersIngress._compose_text("", "", "")
    assert result == ""


def test_parse_tab_delimited():
    output = (
        "rem1\tTask 1\tBody 1\t2026-02-17\t2026-02-18 10:00:00\n"
        "rem2\tTask 2\tBody 2\t2026-02-17\t\n"
        "rem3\tTask 3\t\t\t"
    )
    results = AppleRemindersIngress._parse_tab_delimited(output)
    assert len(results) == 3
    assert results[0]["id"] == "rem1"
    assert results[0]["name"] == "Task 1"
    assert results[0]["body"] == "Body 1"
    assert results[0]["creation_date"] == "2026-02-17"
    assert results[0]["due_date"] == "2026-02-18 10:00:00"

    assert results[1]["id"] == "rem2"
    assert results[1]["due_date"] == ""

    assert results[2]["id"] == "rem3"
    assert results[2]["body"] == ""
    assert results[2]["creation_date"] == ""
    assert results[2]["due_date"] == ""


def test_fetch_new_respects_limit(monkeypatch):
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )
    raw = [
        {"id": f"rem_{i}", "name": f"Task {i}", "body": "", "creation_date": "", "due_date": ""}
        for i in range(10)
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new(limit=3)
    assert len(messages) == 3


def test_context_carries_list_name(monkeypatch):
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="My Custom List",
        owner_sender="+15551234567",
        store=store,
    )
    raw = [
        {"id": "rem_ctx", "name": "Test context", "body": "", "creation_date": "", "due_date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert messages[0].context["list_name"] == "My Custom List"


def test_due_date_future_waits(monkeypatch):
    ingress = AppleRemindersIngress(owner_sender="+15551234567", trigger_tag="!!agent", due_delay_seconds=60)
    raw = [
        {
            "id": "rem_future",
            "name": "Deploy !!agent",
            "body": "",
            "creation_date": "",
            "due_date": _due_in(300),
        },
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)
    assert ingress.fetch_new() == []


def test_due_date_within_delay_waits(monkeypatch):
    ingress = AppleRemindersIngress(owner_sender="+15551234567", trigger_tag="!!agent", due_delay_seconds=60)
    raw = [
        {
            "id": "rem_recent_due",
            "name": "Deploy !!agent",
            "body": "",
            "creation_date": "",
            "due_date": _due_in(-10),
        },
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)
    assert ingress.fetch_new() == []


def test_due_date_past_runs(monkeypatch):
    ingress = AppleRemindersIngress(owner_sender="+15551234567", trigger_tag="!!agent", due_delay_seconds=60)
    raw = [
        {
            "id": "rem_past_due",
            "name": "Deploy !!agent",
            "body": "",
            "creation_date": "",
            "due_date": _due_in(-180),
        },
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)
    messages = ingress.fetch_new()
    assert len(messages) == 1


def test_unparseable_due_date_skips(monkeypatch):
    ingress = AppleRemindersIngress(owner_sender="+15551234567", trigger_tag="!!agent", due_delay_seconds=60)
    raw = [
        {
            "id": "rem_bad_due",
            "name": "Deploy !!agent",
            "body": "",
            "creation_date": "",
            "due_date": "not-a-date",
        },
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)
    assert ingress.fetch_new() == []


def test_parse_due_date_uses_configured_timezone():
    ingress = AppleRemindersIngress(timezone_name="UTC")
    parsed = ingress._parse_due_date("2026-03-01 10:00:00")
    assert parsed is not None
    assert parsed.tzinfo == ZoneInfo("UTC")


def test_due_date_with_configured_timezone_runs(monkeypatch):
    ingress = AppleRemindersIngress(
        owner_sender="+15551234567",
        trigger_tag="!!agent",
        due_delay_seconds=60,
        timezone_name="UTC",
    )
    due_utc = (datetime.now(ZoneInfo("UTC")) - timedelta(seconds=180)).strftime("%Y-%m-%d %H:%M:%S")
    raw = [
        {
            "id": "rem_tz_due",
            "name": "Deploy !!agent",
            "body": "",
            "creation_date": "",
            "due_date": due_utc,
        },
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)
    messages = ingress.fetch_new()
    assert len(messages) == 1


def test_recurrence_runs_new_due_occurrence(monkeypatch):
    ingress = AppleRemindersIngress(owner_sender="+15551234567", trigger_tag="!!agent", due_delay_seconds=60)
    due1 = _due_in(-180)
    due2 = _due_in(300)
    raw = [{"id": "rem_repeat", "name": "Task !!agent", "body": "", "creation_date": "", "due_date": due1}]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    first = ingress.fetch_new()
    assert len(first) == 1
    ingress.mark_processed_occurrence(first[0].context["occurrence_key"])

    raw[0]["due_date"] = due2
    second = ingress.fetch_new()
    assert second == []

    raw[0]["due_date"] = _due_in(-240)
    third = ingress.fetch_new()
    assert len(third) == 1
    assert third[0].context["occurrence_key"] != first[0].context["occurrence_key"]


# --- Trigger Tag Tests ---


def test_trigger_tag_required_skips_without_tag(monkeypatch):
    """Reminders without the trigger tag should be skipped."""
    ingress = AppleRemindersIngress(owner_sender="+15551234567", trigger_tag="!!agent")
    raw = [
        {"id": "rem_1", "name": "Buy milk", "body": "Don't forget", "creation_date": "", "due_date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert messages == []


def test_trigger_tag_in_name_passes_and_stripped(monkeypatch):
    """Reminder with tag in name should be returned with tag stripped."""
    ingress = AppleRemindersIngress(owner_sender="+15551234567", trigger_tag="!!agent")
    raw = [
        {"id": "rem_1", "name": "Buy milk !!agent", "body": "", "creation_date": "", "due_date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert len(messages) == 1
    assert "!!agent" not in messages[0].text
    assert "Buy milk" in messages[0].text


def test_trigger_tag_in_body_passes(monkeypatch):
    """Reminder with tag in body should be returned."""
    ingress = AppleRemindersIngress(owner_sender="+15551234567", trigger_tag="!!agent")
    raw = [
        {"id": "rem_1", "name": "Deploy app", "body": "!!agent push to staging", "creation_date": "", "due_date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert len(messages) == 1
    assert "Deploy app" in messages[0].text


def test_trigger_tag_empty_processes_all(monkeypatch):
    """When trigger_tag is empty, all reminders are processed (backward compat)."""
    ingress = AppleRemindersIngress(owner_sender="+15551234567", trigger_tag="")
    raw = [
        {"id": "rem_1", "name": "Buy milk", "body": "", "creation_date": "", "due_date": ""},
        {"id": "rem_2", "name": "Walk dog", "body": "", "creation_date": "", "due_date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_incomplete_via_applescript", lambda limit: raw)

    messages = ingress.fetch_new()
    assert len(messages) == 2
