"""Tests for the RelayOrchestrator."""

from conftest import FakeConnector, FakeEgress, FakeStore

from codex_relay.commanding import CommandKind
from codex_relay.models import InboundMessage
from codex_relay.orchestrator import RelayOrchestrator


def test_task_command_creates_approval_request():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
    )

    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="task: create a hello world project",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.TASK
    assert result.approval_request_id is not None
    assert any("Approve with" in text for _, text in egress.messages)


def test_chat_requires_prefix_when_enabled():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        require_chat_prefix=True,
        chat_prefix="relay:",
    )

    msg = InboundMessage(
        id="m2",
        sender="+15551234567",
        text="what directory are we in?",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.response == "ignored_missing_chat_prefix"
    assert connector.turns == []
    assert egress.messages == []


def test_chat_with_prefix_runs_turn():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        require_chat_prefix=True,
        chat_prefix="relay:",
    )

    msg = InboundMessage(
        id="m3",
        sender="+15551234567",
        text="relay: what directory are we in?",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.CHAT
    assert result.response == "assistant-response"
    assert connector.turns
    assert egress.messages


def test_clear_context_resets_sender_thread():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        require_chat_prefix=True,
        chat_prefix="relay:",
    )

    msg = InboundMessage(
        id="m4",
        sender="+15551234567",
        text="clear context",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )

    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.CLEAR_CONTEXT
    assert any("fresh chat context" in text for _, text in egress.messages)
    assert "reset:+15551234567" in connector.created
