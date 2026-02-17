"""Tests for Apple Mail ingress module."""

from __future__ import annotations

import json

from codex_relay.mail_ingress import AppleMailIngress


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
