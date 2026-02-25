"""Tests for Apple Mail ingress module."""

from __future__ import annotations

from types import SimpleNamespace

from apple_flow.mail_ingress import AppleMailIngress


def test_extract_email_address_with_angle_brackets():
    result = AppleMailIngress._extract_email_address("John Doe <john@example.com>")
    assert result == "john@example.com"


def test_extract_email_address_plain():
    result = AppleMailIngress._extract_email_address("john@example.com")
    assert result == "john@example.com"


def test_extract_email_address_empty():
    result = AppleMailIngress._extract_email_address("")
    assert result == ""


def test_compose_text_subject_and_body():
    result = AppleMailIngress._compose_text("task: fix the bug", "Details about the bug...")
    assert result == "task: fix the bug\n\nDetails about the bug..."


def test_compose_text_subject_only():
    result = AppleMailIngress._compose_text("relay: hello", "")
    assert result == "relay: hello"


def test_compose_text_body_only():
    result = AppleMailIngress._compose_text("", "Just the body text")
    assert result == "Just the body text"


def test_compose_text_both_empty():
    result = AppleMailIngress._compose_text("", "")
    assert result == ""


def test_fetch_new_skips_non_allowlisted_senders(monkeypatch):
    ingress = AppleMailIngress()
    # With AppleScript filtering, only alice's email would be returned
    raw_messages = [
        {"id": "1", "sender": "alice@example.com", "subject": "relay: hi", "body": "hello", "date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_unread_via_applescript", lambda limit, sender_filter=None: raw_messages)
    monkeypatch.setattr(ingress, "_mark_as_read", lambda ids: None)

    messages = ingress.fetch_new(sender_allowlist=["alice@example.com"])
    assert len(messages) == 1
    assert messages[0].sender == "alice@example.com"


def test_fetch_new_returns_empty_when_require_filter_no_allowlist():
    ingress = AppleMailIngress()
    messages = ingress.fetch_new(sender_allowlist=[], require_sender_filter=True)
    assert messages == []


def test_fetch_new_converts_to_inbound_messages(monkeypatch):
    ingress = AppleMailIngress()
    raw_messages = [
        {
            "id": "42",
            "sender": "Test User <test@example.com>",
            "subject": "task: build feature",
            "body": "Please build the new feature",
            "date": "2025-01-15T10:00:00",
        },
    ]
    monkeypatch.setattr(ingress, "_fetch_unread_via_applescript", lambda limit, sender_filter=None: raw_messages)
    monkeypatch.setattr(ingress, "_mark_as_read", lambda ids: None)

    messages = ingress.fetch_new()
    assert len(messages) == 1
    msg = messages[0]
    assert msg.id == "mail_42"
    assert msg.sender == "test@example.com"
    assert "task: build feature" in msg.text
    assert "Please build the new feature" in msg.text
    assert msg.is_from_me is False


def test_fetch_new_skips_empty_messages(monkeypatch):
    ingress = AppleMailIngress()
    raw_messages = [
        {"id": "1", "sender": "test@example.com", "subject": "", "body": "", "date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_unread_via_applescript", lambda limit, sender_filter=None: raw_messages)
    monkeypatch.setattr(ingress, "_mark_as_read", lambda ids: None)

    messages = ingress.fetch_new()
    assert messages == []


def test_latest_rowid_returns_zero():
    ingress = AppleMailIngress()
    assert ingress.latest_rowid() == 0


def test_fetch_new_marks_messages_as_read(monkeypatch):
    ingress = AppleMailIngress()
    raw_messages = [
        {"id": "10", "sender": "test@example.com", "subject": "relay: hello", "body": "world", "date": ""},
    ]
    marked_ids: list[list[str]] = []
    monkeypatch.setattr(ingress, "_fetch_unread_via_applescript", lambda limit, sender_filter=None: raw_messages)
    monkeypatch.setattr(ingress, "_mark_as_read", lambda ids: marked_ids.append(ids))

    ingress.fetch_new()
    assert len(marked_ids) == 1
    assert "10" in marked_ids[0]


# --- Trigger Tag Tests ---


def test_trigger_tag_required_skips_without_tag(monkeypatch):
    """Emails without the trigger tag should be skipped and NOT marked as read."""
    ingress = AppleMailIngress(trigger_tag="!!agent")
    raw_messages = [
        {"id": "1", "sender": "user@example.com", "subject": "Hello there", "body": "Just saying hi", "date": ""},
    ]
    marked_ids: list[list[str]] = []
    monkeypatch.setattr(ingress, "_fetch_unread_via_applescript", lambda limit, sender_filter=None: raw_messages)
    monkeypatch.setattr(ingress, "_mark_as_read", lambda ids: marked_ids.append(ids))

    messages = ingress.fetch_new()
    assert messages == []
    assert marked_ids == []  # Must NOT be marked as read


def test_trigger_tag_in_subject_passes_and_stripped(monkeypatch):
    """Email with trigger tag in subject should be returned with tag stripped."""
    ingress = AppleMailIngress(trigger_tag="!!agent")
    raw_messages = [
        {"id": "2", "sender": "user@example.com", "subject": "!!agent Deploy to staging", "body": "Details here", "date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_unread_via_applescript", lambda limit, sender_filter=None: raw_messages)
    monkeypatch.setattr(ingress, "_mark_as_read", lambda ids: None)

    messages = ingress.fetch_new()
    assert len(messages) == 1
    assert "!!agent" not in messages[0].text
    assert "Deploy to staging" in messages[0].text


def test_trigger_tag_in_body_passes(monkeypatch):
    """Email with trigger tag in body should be returned."""
    ingress = AppleMailIngress(trigger_tag="!!agent")
    raw_messages = [
        {"id": "3", "sender": "user@example.com", "subject": "Work task", "body": "Please do X\n\n!!agent", "date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_unread_via_applescript", lambda limit, sender_filter=None: raw_messages)
    monkeypatch.setattr(ingress, "_mark_as_read", lambda ids: None)

    messages = ingress.fetch_new()
    assert len(messages) == 1
    assert "Work task" in messages[0].text


def test_trigger_tag_empty_processes_all(monkeypatch):
    """When trigger_tag is empty, all emails are processed (backward compat)."""
    ingress = AppleMailIngress(trigger_tag="")
    raw_messages = [
        {"id": "4", "sender": "a@example.com", "subject": "No tag here", "body": "Content", "date": ""},
        {"id": "5", "sender": "b@example.com", "subject": "Also no tag", "body": "More content", "date": ""},
    ]
    monkeypatch.setattr(ingress, "_fetch_unread_via_applescript", lambda limit, sender_filter=None: raw_messages)
    monkeypatch.setattr(ingress, "_mark_as_read", lambda ids: None)

    messages = ingress.fetch_new()
    assert len(messages) == 2


def test_trigger_tag_only_marks_processed_emails_as_read(monkeypatch):
    """Only emails that pass the trigger tag check should be marked as read."""
    ingress = AppleMailIngress(trigger_tag="!!agent")
    raw_messages = [
        {"id": "10", "sender": "a@example.com", "subject": "!!agent do this", "body": "", "date": ""},
        {"id": "11", "sender": "b@example.com", "subject": "no tag", "body": "skip me", "date": ""},
    ]
    marked_ids: list[list[str]] = []
    monkeypatch.setattr(ingress, "_fetch_unread_via_applescript", lambda limit, sender_filter=None: raw_messages)
    monkeypatch.setattr(ingress, "_mark_as_read", lambda ids: marked_ids.append(list(ids)))

    messages = ingress.fetch_new()
    assert len(messages) == 1
    assert len(marked_ids) == 1
    assert "10" in marked_ids[0]
    assert "11" not in marked_ids[0]


def test_mark_as_read_targets_ids_directly(monkeypatch):
    ingress = AppleMailIngress()
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("apple_flow.mail_ingress.subprocess.run", fake_run)

    ingress._mark_as_read(["42", "43"])

    script = captured["cmd"][2]
    assert 'first message of inbox whose id as text is "42"' in script
    assert 'first message of inbox whose id as text is "43"' in script
    assert "every message of inbox whose read status is false" not in script
    assert captured["kwargs"]["timeout"] == 30
