"""Tests for approval security - sender verification."""

from conftest import FakeConnector, FakeEgress, FakeStore

from codex_relay.commanding import CommandKind
from codex_relay.models import InboundMessage
from codex_relay.orchestrator import RelayOrchestrator


def test_approval_sender_verification_blocks_different_sender():
    """Test that only the original requester can approve their own requests."""
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/tmp"],
        default_workspace="/tmp",
    )

    # First sender creates a task
    msg1 = InboundMessage(
        id="m1",
        sender="+15551111111",
        text="task: create something",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )
    result1 = orchestrator.handle_message(msg1)
    assert result1.kind is CommandKind.TASK
    request_id = result1.approval_request_id
    assert request_id is not None

    # Different sender tries to approve
    egress.messages.clear()
    msg2 = InboundMessage(
        id="m2",
        sender="+15552222222",
        text=f"approve {request_id}",
        received_at="2026-02-16T12:01:00Z",
        is_from_me=False,
    )
    result2 = orchestrator.handle_message(msg2)
    assert result2.kind is CommandKind.APPROVE
    assert "original requester" in result2.response

    # Verify the approval is still pending
    approval = store.get_approval(request_id)
    assert approval is not None
    assert approval["status"] == "pending"


def test_approval_sender_verification_allows_same_sender():
    """Test that the original requester can approve their own requests."""
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/tmp"],
        default_workspace="/tmp",
    )

    sender = "+15551111111"

    # Create a task
    msg1 = InboundMessage(
        id="m1",
        sender=sender,
        text="task: create something",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )
    result1 = orchestrator.handle_message(msg1)
    request_id = result1.approval_request_id
    assert request_id is not None

    # Same sender approves
    egress.messages.clear()
    msg2 = InboundMessage(
        id="m2",
        sender=sender,
        text=f"approve {request_id}",
        received_at="2026-02-16T12:01:00Z",
        is_from_me=False,
    )
    result2 = orchestrator.handle_message(msg2)
    assert result2.kind is CommandKind.APPROVE
    assert "original requester" not in result2.response

    # Verify the approval is now approved
    approval = store.get_approval(request_id)
    assert approval is not None
    assert approval["status"] == "approved"


def test_deny_sender_verification_blocks_different_sender():
    """Test that only the original requester can deny their own requests."""
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/tmp"],
        default_workspace="/tmp",
    )

    # First sender creates a task
    msg1 = InboundMessage(
        id="m1",
        sender="+15551111111",
        text="task: create something",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )
    result1 = orchestrator.handle_message(msg1)
    request_id = result1.approval_request_id

    # Different sender tries to deny
    egress.messages.clear()
    msg2 = InboundMessage(
        id="m2",
        sender="+15552222222",
        text=f"deny {request_id}",
        received_at="2026-02-16T12:01:00Z",
        is_from_me=False,
    )
    result2 = orchestrator.handle_message(msg2)
    assert result2.kind is CommandKind.DENY
    assert "original requester" in result2.response

    # Verify the approval is still pending
    approval = store.get_approval(request_id)
    assert approval["status"] == "pending"


def test_unknown_approval_request():
    """Test handling of unknown request IDs."""
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()

    orchestrator = RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/tmp"],
        default_workspace="/tmp",
    )

    msg = InboundMessage(
        id="m1",
        sender="+15551111111",
        text="approve req_nonexistent",
        received_at="2026-02-16T12:00:00Z",
        is_from_me=False,
    )
    result = orchestrator.handle_message(msg)
    assert result.kind is CommandKind.APPROVE
    assert "Unknown request id" in result.response
