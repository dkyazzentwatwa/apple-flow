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
        "Apple Flow help: system: stop | restart | kill provider | cancel run <run_id> | mute | unmute"
    )
    egress.send("+15551234567", full_text)

    fragment = "system: stop | restart | kill provider | cancel run <run_id>"
    assert egress.was_recent_outbound("+15551234567", fragment)


def test_attachment_echo_marker_tracks_recent_recipients():
    egress = IMessageEgress()
    egress.mark_attachment_outbound("+15551234567")

    assert egress.was_recent_attachment_outbound("+15551234567") is True
    assert egress.was_recent_attachment_outbound("+15550000000") is False


def test_owner_only_auto_sends_intentional_image_results(monkeypatch, tmp_path):
    sent_calls = []
    attachment_calls = []
    image_path = tmp_path / "result.png"
    image_path.write_bytes(b"png")

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    def fake_send_attachment(recipient: str, file_path: str) -> dict[str, object]:
        attachment_calls.append((recipient, file_path))
        return {"ok": True}

    egress = IMessageEgress(
        auto_send_image_results="owner-only",
        image_result_owner_number="+15551234567",
    )
    monkeypatch.setattr(egress, "_osascript_send", fake_send)
    monkeypatch.setattr("apple_flow.egress._send_imessage_attachment", fake_send_attachment)

    egress.send("+15551234567", f"Build finished.\n{image_path}")

    assert attachment_calls == [("+15551234567", str(image_path))]
    assert sent_calls == [("+15551234567", "Build finished.")]
    assert egress.was_recent_attachment_outbound("+15551234567") is True


def test_owner_only_does_not_auto_send_for_other_recipients(monkeypatch, tmp_path):
    sent_calls = []
    attachment_calls = []
    image_path = tmp_path / "result.png"
    image_path.write_bytes(b"png")

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    def fake_send_attachment(recipient: str, file_path: str) -> dict[str, object]:
        attachment_calls.append((recipient, file_path))
        return {"ok": True}

    egress = IMessageEgress(
        auto_send_image_results="owner-only",
        image_result_owner_number="+15551234567",
    )
    monkeypatch.setattr(egress, "_osascript_send", fake_send)
    monkeypatch.setattr("apple_flow.egress._send_imessage_attachment", fake_send_attachment)

    outbound = f"Build finished.\n{image_path}"
    egress.send("+15550000000", outbound)

    assert attachment_calls == []
    assert sent_calls == [("+15550000000", outbound)]


def test_auto_send_ignores_inline_image_paths_in_prose(monkeypatch, tmp_path):
    sent_calls = []
    attachment_calls = []
    image_path = tmp_path / "result.png"
    image_path.write_bytes(b"png")

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    def fake_send_attachment(recipient: str, file_path: str) -> dict[str, object]:
        attachment_calls.append((recipient, file_path))
        return {"ok": True}

    egress = IMessageEgress(auto_send_image_results="allowed-senders")
    monkeypatch.setattr(egress, "_osascript_send", fake_send)
    monkeypatch.setattr("apple_flow.egress._send_imessage_attachment", fake_send_attachment)

    outbound = f"See {image_path} for details."
    egress.send("+15551234567", outbound)

    assert attachment_calls == []
    assert sent_calls == [("+15551234567", outbound)]


def test_auto_send_ignores_image_paths_inside_code_fences(monkeypatch, tmp_path):
    sent_calls = []
    attachment_calls = []
    image_path = tmp_path / "result.png"
    image_path.write_bytes(b"png")

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    def fake_send_attachment(recipient: str, file_path: str) -> dict[str, object]:
        attachment_calls.append((recipient, file_path))
        return {"ok": True}

    egress = IMessageEgress(auto_send_image_results="allowed-senders")
    monkeypatch.setattr(egress, "_osascript_send", fake_send)
    monkeypatch.setattr("apple_flow.egress._send_imessage_attachment", fake_send_attachment)

    outbound = f"```text\n{image_path}\n```"
    egress.send("+15551234567", outbound)

    assert attachment_calls == []
    assert sent_calls == [("+15551234567", outbound)]


def test_auto_send_accepts_saved_image_markdown_link_format(monkeypatch, tmp_path):
    sent_calls = []
    attachment_calls = []
    image_path = tmp_path / "result.jpg"
    image_path.write_bytes(b"jpg")

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    def fake_send_attachment(recipient: str, file_path: str) -> dict[str, object]:
        attachment_calls.append((recipient, file_path))
        return {"ok": True}

    egress = IMessageEgress(auto_send_image_results="allowed-senders")
    monkeypatch.setattr(egress, "_osascript_send", fake_send)
    monkeypatch.setattr("apple_flow.egress._send_imessage_attachment", fake_send_attachment)

    outbound = f"Saved image: [macbook-neo-citrus.jpg]({image_path})"
    egress.send("+15551234567", outbound)

    assert attachment_calls == [("+15551234567", str(image_path))]
    assert sent_calls == [("+15551234567", "Attached image.")]


def test_auto_send_limits_images_to_three(monkeypatch, tmp_path):
    sent_calls = []
    attachment_calls = []
    image_paths = []
    for idx in range(4):
        image_path = tmp_path / f"result-{idx}.png"
        image_path.write_bytes(b"png")
        image_paths.append(image_path)

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    def fake_send_attachment(recipient: str, file_path: str) -> dict[str, object]:
        attachment_calls.append((recipient, file_path))
        return {"ok": True}

    egress = IMessageEgress(auto_send_image_results="allowed-senders")
    monkeypatch.setattr(egress, "_osascript_send", fake_send)
    monkeypatch.setattr("apple_flow.egress._send_imessage_attachment", fake_send_attachment)

    outbound = "\n".join(str(path) for path in image_paths)
    egress.send("+15551234567", outbound)

    assert attachment_calls == [("+15551234567", str(path)) for path in image_paths[:3]]
    assert sent_calls == [("+15551234567", "Attached 3 of 4 images.")]


def test_auto_send_falls_back_to_original_text_when_attachment_send_fails(monkeypatch, tmp_path):
    sent_calls = []
    image_path = tmp_path / "result.png"
    image_path.write_bytes(b"png")

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    def fake_send_attachment(_recipient: str, _file_path: str) -> dict[str, object]:
        return {"ok": False, "error": "Messages unavailable"}

    egress = IMessageEgress(auto_send_image_results="allowed-senders")
    monkeypatch.setattr(egress, "_osascript_send", fake_send)
    monkeypatch.setattr("apple_flow.egress._send_imessage_attachment", fake_send_attachment)

    outbound = f"Build finished.\n{image_path}"
    egress.send("+15551234567", outbound)

    assert sent_calls == [("+15551234567", outbound)]
