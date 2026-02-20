"""Tests verifying orchestrator logs AI completions to Apple Notes."""

from unittest.mock import MagicMock

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.commanding import CommandKind
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator

_WS = "/tmp/testws"


def _make_msg(text, id="m1"):
    return InboundMessage(
        id=id,
        sender="+15551234567",
        text=text,
        received_at="2026-02-17T10:00:00Z",
        is_from_me=False,
        context={},
    )


def _make_orc(log_notes_egress=None):
    """Build orchestrator using the conftest fake implementations."""
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        allowed_workspaces=[_WS],
        default_workspace=_WS,
        require_chat_prefix=False,
        log_notes_egress=log_notes_egress,
        notes_log_folder_name="codex-logs",
    )


def test_non_mutating_response_calls_create_log_note():
    """Non-mutating responses (idea/plan/chat) write a log note."""
    mock_log = MagicMock()
    mock_log.create_log_note.return_value = True

    orc = _make_orc(log_notes_egress=mock_log)
    orc.handle_message(_make_msg("idea: brainstorm auth options"))

    mock_log.create_log_note.assert_called_once()
    kwargs = mock_log.create_log_note.call_args[1]
    assert kwargs["folder_name"] == "codex-logs"
    assert "idea" in kwargs["title"].lower()
    assert "brainstorm auth options" in kwargs["body"]


def test_no_log_note_when_log_egress_is_none():
    """When log_notes_egress is None, no error and no call."""
    orc = _make_orc(log_notes_egress=None)
    result = orc.handle_message(_make_msg("plan: write a test plan"))
    assert result.kind is CommandKind.PLAN  # no exception raised


def test_task_completion_calls_create_log_note():
    """Task queuing logs the plan, and execution logs the final output."""
    mock_log = MagicMock()
    mock_log.create_log_note.return_value = True

    orc = _make_orc(log_notes_egress=mock_log)

    # Submit task
    result = orc.handle_message(_make_msg("task: create hello world", id="t1"))
    assert result.kind is CommandKind.TASK
    request_id = result.approval_request_id
    assert request_id

    # Logged once when plan is created and approval iMessage is sent
    mock_log.create_log_note.assert_called_once()
    plan_body = mock_log.create_log_note.call_args[1]["body"]
    assert "approve" in plan_body.lower() or "plan" in plan_body.lower()

    # Approve → executes → logs a second time with the final output
    orc.handle_message(_make_msg(f"approve {request_id}", id="a1"))
    assert mock_log.create_log_note.call_count == 2
    exec_body = mock_log.create_log_note.call_args[1]["body"]
    assert "Execution" in exec_body or "Response" in exec_body
