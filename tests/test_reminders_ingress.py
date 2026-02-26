"""Tests for Apple Reminders ingress module."""

from __future__ import annotations

import json

from conftest import FakeStore

from apple_flow.reminders_ingress import AppleRemindersIngress


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


def test_fetch_new_skips_already_processed(monkeypatch):
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )
    # Pre-mark rem_001 as processed.
    ingress.mark_processed("rem_001")

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


def test_mark_processed_persists_to_store():
    store = FakeStore()
    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )

    ingress.mark_processed("rem_001")
    ingress.mark_processed("rem_002")

    # Verify persisted to store.
    raw = store.get_state("reminders_processed_ids")
    assert raw is not None
    ids = json.loads(raw)
    assert "rem_001" in ids
    assert "rem_002" in ids


def test_processed_ids_hydrated_from_store():
    store = FakeStore()
    store.set_state("reminders_processed_ids", json.dumps(["rem_old_1", "rem_old_2"]))

    ingress = AppleRemindersIngress(
        list_name="agent-task",
        owner_sender="+15551234567",
        store=store,
    )
    assert "rem_old_1" in ingress._processed_ids
    assert "rem_old_2" in ingress._processed_ids


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
    # Test normal, empty, and missing-like fields
    output = (
        "rem1\tTask 1\tBody 1\t2026-02-17\t2026-02-18\n"
        "rem2\tTask 2\tBody 2\t2026-02-17\t\n"
        "rem3\tTask 3\t\t\t"
    )
    results = AppleRemindersIngress._parse_tab_delimited(output)
    assert len(results) == 3
    assert results[0]["id"] == "rem1"
    assert results[0]["name"] == "Task 1"
    assert results[0]["body"] == "Body 1"
    assert results[0]["creation_date"] == "2026-02-17"
    assert results[0]["due_date"] == "2026-02-18"

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
