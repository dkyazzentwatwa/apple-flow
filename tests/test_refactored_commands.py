from unittest.mock import MagicMock

import pytest

from apple_flow.commanding import CommandKind, ParsedCommand
from apple_flow.commands import COMMAND_HANDLERS
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


@pytest.fixture
def mock_orchestrator():
    orchestrator = MagicMock(spec=RelayOrchestrator)
    orchestrator.store = MagicMock()
    orchestrator.egress = MagicMock()
    orchestrator.connector = MagicMock()
    orchestrator.log_file_path = None
    return orchestrator

def test_health_command_handler(mock_orchestrator):
    message = InboundMessage(id="1", sender="+1234567890", text="health", received_at="2024-01-01T00:00:00Z", is_from_me=False)
    command = ParsedCommand(kind=CommandKind.HEALTH, payload="")

    mock_orchestrator.store.get_stats.return_value = {"active_sessions": 5, "total_messages": 100, "pending_approvals": 2}
    mock_orchestrator.store.get_state.return_value = None

    response = COMMAND_HANDLERS[CommandKind.HEALTH].handle(mock_orchestrator, message, command)

    assert "Apple Flow Health" in response
    assert "Sessions: 5" in response
    mock_orchestrator.egress.send.assert_called_once()

def test_status_command_handler(mock_orchestrator):
    message = InboundMessage(id="1", sender="+1234567890", text="status", received_at="2024-01-01T00:00:00Z", is_from_me=False)
    command = ParsedCommand(kind=CommandKind.STATUS, payload="")

    mock_orchestrator.store.list_pending_approvals.return_value = [
        {"request_id": "req_1", "command_preview": "test command"}
    ]

    response = COMMAND_HANDLERS[CommandKind.STATUS].handle(mock_orchestrator, message, command)

    assert "Pending approvals (1)" in response
    assert "req_1" in response
    mock_orchestrator.egress.send.assert_called_once()
