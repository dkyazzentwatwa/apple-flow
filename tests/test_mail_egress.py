"""Tests for Apple Mail egress module."""

from __future__ import annotations

import time

from apple_flow.mail_egress import AppleMailEgress


def test_suppresses_duplicate_outbound_within_window(monkeypatch):
    sent_calls: list[tuple[str, str, str]] = []

    def fake_send(_recipient: str, _subject: str, _body: str) -> None:
        sent_calls.append((_recipient, _subject, _body))

    egress = AppleMailEgress(suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send("test@example.com", "Hello world")
    egress.send("test@example.com", "Hello world")

    assert len(sent_calls) == 1


def test_sends_different_messages(monkeypatch):
    sent_calls: list[tuple[str, str, str]] = []

    def fake_send(_recipient: str, _subject: str, _body: str) -> None:
        sent_calls.append((_recipient, _subject, _body))

    egress = AppleMailEgress(suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send("test@example.com", "Hello")
    egress.send("test@example.com", "Goodbye")

    assert len(sent_calls) == 2


def test_default_response_subject_is_agent(monkeypatch):
    sent_calls: list[tuple[str, str, str]] = []

    def fake_send(_recipient: str, _subject: str, _body: str) -> None:
        sent_calls.append((_recipient, _subject, _body))

    egress = AppleMailEgress()
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send("test@example.com", "Hello")
    assert sent_calls
    assert sent_calls[0][1] == "AGENT:"


def test_custom_response_subject_used(monkeypatch):
    sent_calls: list[tuple[str, str, str]] = []

    def fake_send(_recipient: str, _subject: str, _body: str) -> None:
        sent_calls.append((_recipient, _subject, _body))

    egress = AppleMailEgress(response_subject="Custom Subject")
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send("test@example.com", "Hello")
    assert sent_calls
    assert sent_calls[0][1] == "Custom Subject"


def test_chunking_large_messages():
    egress = AppleMailEgress(max_chunk_chars=100)
    chunks = egress._chunk("x" * 250)
    assert len(chunks) == 3
    assert chunks[0] == "x" * 100
    assert chunks[1] == "x" * 100
    assert chunks[2] == "x" * 50


def test_no_chunking_small_messages():
    egress = AppleMailEgress(max_chunk_chars=100)
    chunks = egress._chunk("hello")
    assert len(chunks) == 1
    assert chunks[0] == "hello"


def test_chunked_messages_keep_same_subject(monkeypatch):
    sent_calls: list[tuple[str, str, str]] = []

    def fake_send(_recipient: str, _subject: str, _body: str) -> None:
        sent_calls.append((_recipient, _subject, _body))

    egress = AppleMailEgress(max_chunk_chars=5)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send("test@example.com", "abcdefghij")
    assert len(sent_calls) > 1
    assert all(call[1] == "AGENT:" for call in sent_calls)


def test_send_uses_reply_threading_for_mail_context(monkeypatch):
    reply_calls: list[tuple[str, str, str, str]] = []
    send_calls: list[tuple[str, str, str]] = []

    def fake_reply(_recipient: str, _message_id: str, _subject: str, _body: str) -> None:
        reply_calls.append((_recipient, _message_id, _subject, _body))

    def fake_send(_recipient: str, _subject: str, _body: str) -> None:
        send_calls.append((_recipient, _subject, _body))

    egress = AppleMailEgress(signature="")
    monkeypatch.setattr(egress, "_osascript_reply", fake_reply)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send(
        "test@example.com",
        "hello",
        context={
            "channel": "mail",
            "mail_message_id": "123",
            "mail_subject_sanitized": "!!agent Deploy to staging".replace("!!agent", "").strip(),
        },
    )

    assert len(reply_calls) == 1
    assert send_calls == []
    assert reply_calls[0][1] == "123"
    assert reply_calls[0][2] == "Re: Deploy to staging"


def test_send_falls_back_to_new_email_when_reply_fails(monkeypatch):
    send_calls: list[tuple[str, str, str]] = []

    def failing_reply(_recipient: str, _message_id: str, _subject: str, _body: str) -> None:
        raise RuntimeError("boom")

    def fake_send(_recipient: str, _subject: str, _body: str) -> None:
        send_calls.append((_recipient, _subject, _body))

    egress = AppleMailEgress(signature="")
    monkeypatch.setattr(egress, "_osascript_reply", failing_reply)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send(
        "test@example.com",
        "hello",
        context={"channel": "mail", "mail_message_id": "123", "mail_subject_sanitized": "deploy"},
    )

    assert len(send_calls) == 1
    assert send_calls[0][1] == "Re: deploy"


def test_osascript_reply_uses_reply_threading(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return None

    monkeypatch.setattr("apple_flow.mail_egress.subprocess.run", fake_run)
    egress = AppleMailEgress()
    egress._osascript_reply("test@example.com", "123", "Re: hello", "hello")

    script = str(captured["cmd"][2])
    assert "reply originalMessage" in script
    assert "id is 123" in script


def test_echo_detection():
    egress = AppleMailEgress(echo_window_seconds=300.0)
    egress.mark_outbound("test@example.com", "some response")
    assert egress.was_recent_outbound("test@example.com", "some response") is True
    assert egress.was_recent_outbound("test@example.com", "different text") is False


def test_fingerprint_includes_mail_prefix():
    egress = AppleMailEgress()
    fp = egress._fingerprint("test@example.com", "hello")
    # Mail fingerprints should differ from iMessage fingerprints
    assert len(fp) == 64  # SHA256 hex digest


def test_gc_removes_expired_entries():
    egress = AppleMailEgress(echo_window_seconds=0.0)
    egress._recent_fingerprints["old_fp"] = time.time() - 1
    egress._gc_recent()
    assert "old_fp" not in egress._recent_fingerprints


def test_normalize_text():
    result = AppleMailEgress._normalize_text("  Hello\u2019s  World  ")
    assert result == "hello's world"


def test_signature_newlines_decoded():
    egress = AppleMailEgress(signature="\\n\\nFoo")
    assert egress.signature == "\n\nFoo"


def test_echo_detection_with_re_prefix_and_signature():
    """Bounced reply with 'Re: subject\n\n' prefix and appended signature is detected."""
    sig = "\n\n—\nApple Flow 🤖, Your 24/7 Assistant"
    egress = AppleMailEgress(echo_window_seconds=300.0, signature=sig)
    egress.mark_outbound("test@example.com", "response")
    bounced = "Re: Some Subject\n\nresponse" + sig
    assert egress.was_recent_outbound("test@example.com", bounced) is True


def test_echo_detection_body_with_signature_only():
    """Text that is exactly response+signature is detected via the signature fingerprint."""
    sig = "\n\n—\nApple Flow 🤖, Your 24/7 Assistant"
    egress = AppleMailEgress(echo_window_seconds=300.0, signature=sig)
    egress.mark_outbound("test@example.com", "response")
    assert egress.was_recent_outbound("test@example.com", "response" + sig) is True


def test_non_echo_with_newlines_not_detected():
    """Unrelated text containing \\n\\n is not falsely flagged as echo."""
    sig = "\n\n—\nApple Flow 🤖, Your 24/7 Assistant"
    egress = AppleMailEgress(echo_window_seconds=300.0, signature=sig)
    egress.mark_outbound("test@example.com", "response")
    unrelated = "Something else\n\ncompletely different"
    assert egress.was_recent_outbound("test@example.com", unrelated) is False
