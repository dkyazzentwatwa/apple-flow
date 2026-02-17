"""Tests for progress streaming during long tasks."""

from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field

from codex_relay.commanding import CommandKind
from codex_relay.models import InboundMessage
from codex_relay.orchestrator import RelayOrchestrator

from conftest import FakeEgress, FakeStore


@dataclass
class StreamingConnector:
    """Fake connector that supports streaming."""

    created: list[str] = field(default_factory=list)
    turns: list[tuple[str, str]] = field(default_factory=list)
    stream_calls: list[tuple[str, str]] = field(default_factory=list)

    def get_or_create_thread(self, sender: str) -> str:
        self.created.append(sender)
        return "thread_abc"

    def reset_thread(self, sender: str) -> str:
        return sender

    def run_turn(self, thread_id: str, prompt: str) -> str:
        self.turns.append((thread_id, prompt))
        if "planner" in prompt:
            return "PLAN: step 1, step 2"
        if "verifier" in prompt:
            return "VERIFIED: all checks pass"
        return "response"

    def run_turn_streaming(self, thread_id: str, prompt: str, on_progress=None) -> str:
        self.stream_calls.append((thread_id, prompt))
        lines = ["Line 1: starting...\n", "Line 2: processing...\n", "Line 3: done.\n"]
        for line in lines:
            if on_progress:
                on_progress(line)
        return "Streaming result: all done"

    def ensure_started(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


def _make_orchestrator(enable_streaming=True, progress_interval=0.0):
    return RelayOrchestrator(
        connector=StreamingConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
        enable_progress_streaming=enable_streaming,
        progress_update_interval_seconds=progress_interval,
    )


def test_streaming_used_for_approved_execution():
    orch = _make_orchestrator(enable_streaming=True, progress_interval=0.0)

    # Create a task that needs approval
    msg = InboundMessage(
        id="m1", sender="+15551234567", text="task: deploy code",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert result.approval_request_id is not None

    # Approve it
    approve_msg = InboundMessage(
        id="m2", sender="+15551234567", text=f"approve {result.approval_request_id}",
        received_at="2026-02-17T12:01:00Z", is_from_me=False,
    )
    approve_result = orch.handle_message(approve_msg)

    # Streaming connector should have been used
    assert len(orch.connector.stream_calls) == 1
    assert "Streaming result" in approve_result.response


def test_streaming_disabled_uses_regular_run():
    orch = _make_orchestrator(enable_streaming=False)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="task: deploy code",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)
    approve_msg = InboundMessage(
        id="m2", sender="+15551234567", text=f"approve {result.approval_request_id}",
        received_at="2026-02-17T12:01:00Z", is_from_me=False,
    )
    orch.handle_message(approve_msg)

    # Should NOT use streaming
    assert len(orch.connector.stream_calls) == 0
    # Regular turns should be used instead
    assert len(orch.connector.turns) > 0


def test_progress_sends_updates_to_sender():
    orch = _make_orchestrator(enable_streaming=True, progress_interval=0.0)

    msg = InboundMessage(
        id="m1", sender="+15551234567", text="task: deploy code",
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )
    result = orch.handle_message(msg)
    approve_msg = InboundMessage(
        id="m2", sender="+15551234567", text=f"approve {result.approval_request_id}",
        received_at="2026-02-17T12:01:00Z", is_from_me=False,
    )
    orch.handle_message(approve_msg)

    # Check that progress updates were sent
    progress_messages = [text for _, text in orch.egress.messages if "[Progress]" in text]
    assert len(progress_messages) > 0
