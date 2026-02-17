"""Tests for file attachment support."""

from codex_relay.commanding import CommandKind
from codex_relay.models import InboundMessage
from codex_relay.orchestrator import RelayOrchestrator

from conftest import FakeConnector, FakeEgress, FakeStore


def _make_orchestrator(enable_attachments=True):
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
        enable_attachments=enable_attachments,
    )


def test_attachment_context_injected_into_prompt():
    orch = _make_orchestrator(enable_attachments=True)

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
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.IDEA

    _, prompt = orch.connector.turns[0]
    assert "Attached files:" in prompt
    assert "data.csv" in prompt
    assert "text/csv" in prompt


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
    assert "Attached files:" not in prompt


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
    assert "Attached files:" not in prompt


def test_multiple_attachments_all_listed():
    orch = _make_orchestrator(enable_attachments=True)

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


def test_egress_send_attachment():
    """Test egress send_attachment method exists and handles empty path."""
    from codex_relay.egress import IMessageEgress

    egress = IMessageEgress()
    # Empty path should return without error
    egress.send_attachment("+15551234567", "")
