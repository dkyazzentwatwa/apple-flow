from apple_flow.egress import IMessageEgress


def test_suppresses_duplicate_outbound_within_window(monkeypatch):
    sent_calls = []

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    egress = IMessageEgress(suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send("+15551234567", "Hello world")
    egress.send("+15551234567", "Hello world")

    assert len(sent_calls) == 1


def test_chunked_send_marks_full_text_for_echo_detection(monkeypatch):
    sent_calls = []

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    egress = IMessageEgress(max_chunk_chars=10, suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    text = "0123456789ABCDEFGHIJ"  # 2 chunks
    egress.send("+15551234567", text)

    assert len(sent_calls) == 2
    assert egress.was_recent_outbound("+15551234567", text)
    assert egress.was_recent_outbound("+15551234567", "0123456789")

    # Duplicate full payload should be suppressed even when original send chunked.
    egress.send("+15551234567", text)
    assert len(sent_calls) == 2


def test_was_recent_outbound_matches_long_fragment(monkeypatch):
    sent_calls = []

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    egress = IMessageEgress(max_chunk_chars=1200, suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    full_text = (
        "Here's my plan: build, test, and deploy safely with guardrails. "
        "This response is intentionally long to simulate chunked iMessage output. "
        * 20
    )
    egress.send("+15551234567", full_text)

    fragment = full_text[180:760]
    assert egress.was_recent_outbound("+15551234567", fragment)
    # Simulate attributedBody decoding drift that can drop a leading character.
    assert egress.was_recent_outbound("+15551234567", fragment[1:])


def test_was_recent_outbound_matches_medium_fragment(monkeypatch):
    sent_calls = []

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    egress = IMessageEgress(max_chunk_chars=1200, suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    full_text = (
        "Apple Flow help: system: stop | restart | kill provider | cancel run <run_id> | mute | unmute | sync office"
    )
    egress.send("+15551234567", full_text)

    fragment = "system: stop | restart | kill provider | cancel run <run_id>"
    assert egress.was_recent_outbound("+15551234567", fragment)


def test_attachment_echo_marker_tracks_recent_recipients():
    egress = IMessageEgress()
    egress.mark_attachment_outbound("+15551234567")

    assert egress.was_recent_attachment_outbound("+15551234567") is True
    assert egress.was_recent_attachment_outbound("+15550000000") is False
