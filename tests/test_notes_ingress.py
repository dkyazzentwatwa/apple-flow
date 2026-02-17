"""Tests for Apple Notes ingress."""

import json
from unittest.mock import patch, MagicMock

from codex_relay.notes_ingress import AppleNotesIngress

from conftest import FakeStore


def _make_ingress(store=None, auto_approve=False):
    return AppleNotesIngress(
        folder_name="Codex Inbox",
        owner_sender="+15551234567",
        auto_approve=auto_approve,
        store=store,
    )


def _mock_applescript_output(notes):
    """Create mock subprocess result with notes JSON output."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = json.dumps(notes)
    result.stderr = ""
    return result


# --- Fetch Tests ---


@patch("codex_relay.notes_ingress.subprocess.run")
def test_fetch_new_returns_messages(mock_run):
    notes = [
        {"id": "note1", "name": "task: Fix login bug", "body": "Login fails on mobile", "modification_date": "2026-02-17T10:00:00Z"},
        {"id": "note2", "name": "Deploy updates", "body": "Push latest to production", "modification_date": "2026-02-17T11:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(notes)

    ingress = _make_ingress()
    messages = ingress.fetch_new()

    assert len(messages) == 2
    assert messages[0].sender == "+15551234567"
    assert "Fix login bug" in messages[0].text
    assert messages[0].context["channel"] == "notes"
    assert messages[0].context["note_id"] == "note1"


@patch("codex_relay.notes_ingress.subprocess.run")
def test_fetch_skips_processed_ids(mock_run):
    notes = [
        {"id": "note1", "name": "task: Fix bug", "body": "Details", "modification_date": "2026-02-17T10:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(notes)

    ingress = _make_ingress()
    ingress._processed_ids.add("note1")
    messages = ingress.fetch_new()

    assert len(messages) == 0


@patch("codex_relay.notes_ingress.subprocess.run")
def test_fetch_adds_task_prefix_when_no_command_prefix(mock_run):
    notes = [
        {"id": "note1", "name": "Fix the login", "body": "Details", "modification_date": "2026-02-17T10:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(notes)

    ingress = _make_ingress(auto_approve=False)
    messages = ingress.fetch_new()

    assert messages[0].text.startswith("task:")


@patch("codex_relay.notes_ingress.subprocess.run")
def test_fetch_adds_relay_prefix_when_auto_approve(mock_run):
    notes = [
        {"id": "note1", "name": "Fix the login", "body": "Details", "modification_date": "2026-02-17T10:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(notes)

    ingress = _make_ingress(auto_approve=True)
    messages = ingress.fetch_new()

    assert messages[0].text.startswith("relay:")


@patch("codex_relay.notes_ingress.subprocess.run")
def test_fetch_preserves_existing_command_prefix(mock_run):
    notes = [
        {"id": "note1", "name": "idea: brainstorm features", "body": "List options", "modification_date": "2026-02-17T10:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(notes)

    ingress = _make_ingress()
    messages = ingress.fetch_new()

    # Should NOT double-prefix
    assert messages[0].text.startswith("idea:")
    assert not messages[0].text.startswith("task: idea:")


@patch("codex_relay.notes_ingress.subprocess.run")
def test_fetch_skips_empty_notes(mock_run):
    notes = [
        {"id": "note1", "name": "", "body": "", "modification_date": "2026-02-17T10:00:00Z"},
    ]
    mock_run.return_value = _mock_applescript_output(notes)

    ingress = _make_ingress()
    messages = ingress.fetch_new()

    assert len(messages) == 0


# --- Mark Processed Tests ---


def test_mark_processed_persists_to_store():
    store = FakeStore()
    ingress = _make_ingress(store=store)

    ingress.mark_processed("note123")

    assert "note123" in ingress._processed_ids
    raw = store.get_state("notes_processed_ids")
    assert raw is not None
    assert "note123" in json.loads(raw)


# --- Processed IDs Loaded from Store ---


def test_processed_ids_loaded_from_store():
    store = FakeStore()
    store.set_state("notes_processed_ids", json.dumps(["note1", "note2"]))

    ingress = _make_ingress(store=store)

    assert "note1" in ingress._processed_ids
    assert "note2" in ingress._processed_ids


# --- AppleScript Error Handling ---


@patch("codex_relay.notes_ingress.subprocess.run")
def test_fetch_handles_applescript_error(mock_run):
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    result.stderr = "error"
    mock_run.return_value = result

    ingress = _make_ingress()
    messages = ingress.fetch_new()

    assert messages == []


@patch("codex_relay.notes_ingress.subprocess.run")
def test_fetch_handles_timeout(mock_run):
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=30)

    ingress = _make_ingress()
    messages = ingress.fetch_new()

    assert messages == []


@patch("codex_relay.notes_ingress.subprocess.run")
def test_fetch_handles_invalid_json(mock_run):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "not valid json"
    result.stderr = ""
    mock_run.return_value = result

    ingress = _make_ingress()
    messages = ingress.fetch_new()

    assert messages == []


# --- Compose Text ---


def test_compose_text_title_and_body():
    assert AppleNotesIngress._compose_text("Title", "Body") == "Title\n\nBody"


def test_compose_text_title_only():
    assert AppleNotesIngress._compose_text("Title", "") == "Title"


def test_compose_text_body_only():
    assert AppleNotesIngress._compose_text("", "Body") == "Body"


def test_compose_text_both_empty():
    assert AppleNotesIngress._compose_text("", "") == ""
