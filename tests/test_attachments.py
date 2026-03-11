"""Tests for file attachment support."""

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.attachments import AttachmentProcessor
from apple_flow.commanding import CommandKind
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


def _make_orchestrator(enable_attachments=True, attachment_processor=None):
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
        enable_attachments=enable_attachments,
        attachment_processor=attachment_processor,
    )


def test_attachment_context_injected_into_prompt(tmp_path):
    file_path = tmp_path / "data.csv"
    file_path.write_text("name,score\nalice,99\n", encoding="utf-8")
    orch = _make_orchestrator(
        enable_attachments=True,
        attachment_processor=AttachmentProcessor(),
    )

    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="idea: analyze this file",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
        context={
            "attachments": [
                {
                    "filename": "data.csv",
                    "mime_type": "text/csv",
                    "path": str(file_path),
                    "size_bytes": "1024",
                }
            ]
        },
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.IDEA

    _, prompt = orch.connector.turns[0]
    assert "Attached files (processed):" in prompt
    assert "data.csv" in prompt
    assert "text/csv" in prompt
    assert "alice,99" in prompt


def test_attachment_context_not_injected_when_disabled():
    orch = _make_orchestrator(enable_attachments=False)

    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="idea: analyze this file",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
        context={
            "attachments": [
                {
                    "filename": "data.csv",
                    "mime_type": "text/csv",
                    "path": "/tmp/data.csv",
                    "size_bytes": "1024",
                }
            ]
        },
    )
    orch.handle_message(msg)
    _, prompt = orch.connector.turns[0]
    assert "Attached files (processed):" not in prompt


def test_no_attachments_no_injection():
    orch = _make_orchestrator(enable_attachments=True)

    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="idea: just a question",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
    )
    orch.handle_message(msg)
    _, prompt = orch.connector.turns[0]
    assert "Attached files (processed):" not in prompt


def test_multiple_attachments_all_listed():
    orch = _make_orchestrator(
        enable_attachments=True,
        attachment_processor=AttachmentProcessor(),
    )

    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="idea: analyze these",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
        context={
            "attachments": [
                {"filename": "file1.txt", "mime_type": "text/plain", "path": "/tmp/file1.txt", "size_bytes": "100"},
                {"filename": "image.png", "mime_type": "image/png", "path": "/tmp/image.png", "size_bytes": "50000"},
            ]
        },
    )
    orch.handle_message(msg)
    _, prompt = orch.connector.turns[0]
    assert "file1.txt" in prompt
    assert "image.png" in prompt
    assert "status=missing_file" in prompt


def test_empty_text_with_attachments_is_auto_routed_to_chat(tmp_path):
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello from file", encoding="utf-8")

    orch = RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=True,
        chat_prefix="relay:",
        enable_attachments=True,
        attachment_processor=AttachmentProcessor(),
    )

    msg = InboundMessage(
        id="m-empty-with-att",
        sender="+15551234567",
        text="",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
        context={
            "attachments": [
                {
                    "filename": "note.txt",
                    "mime_type": "text/plain",
                    "path": str(file_path),
                    "size_bytes": "64",
                }
            ]
        },
    )

    result = orch.handle_message(msg)

    assert result.kind is CommandKind.CHAT
    assert msg.text.startswith("relay:")
    assert orch.connector.turns
    _, prompt = orch.connector.turns[0]
    assert "Attached files (processed):" in prompt
    assert "note.txt" in prompt


def test_image_attachment_triggers_analysis_instruction():
    # No AttachmentProcessor — exercises the fallback image path in _inject_attachment_context
    orch = _make_orchestrator(enable_attachments=True)

    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="what did I eat?",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
        context={
            "attachments": [
                {
                    "filename": "IMG_1234.heic",
                    "mime_type": "image/heic",
                    "path": "/tmp/IMG_1234.heic",
                    "size_bytes": "2048000",
                }
            ]
        },
    )
    orch.handle_message(msg)
    _, prompt = orch.connector.turns[0]
    assert "/tmp/IMG_1234.heic" in prompt
    assert "visually analyze" in prompt
    assert "Attached files:" not in prompt


def test_non_image_attachment_uses_files_section():
    # No AttachmentProcessor — exercises the fallback non-image path
    orch = _make_orchestrator(enable_attachments=True)

    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="idea: check this doc",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
        context={
            "attachments": [
                {
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "path": "/tmp/report.pdf",
                    "size_bytes": "512000",
                }
            ]
        },
    )
    orch.handle_message(msg)
    _, prompt = orch.connector.turns[0]
    assert "Attached files:" in prompt
    assert "report.pdf" in prompt
    assert "visually analyze" not in prompt
