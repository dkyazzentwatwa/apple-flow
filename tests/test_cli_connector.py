"""Tests for CLI connector."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

import pytest

from codex_relay.codex_cli_connector import CodexCliConnector


def test_cli_connector_implements_protocol():
    """Verify CLI connector implements ConnectorProtocol."""
    from codex_relay.protocols import ConnectorProtocol

    connector = CodexCliConnector()
    assert isinstance(connector, ConnectorProtocol)


def test_ensure_started_is_noop():
    """Ensure started is a no-op for CLI connector."""
    connector = CodexCliConnector()
    # Should not raise
    connector.ensure_started()


def test_get_or_create_thread_returns_sender():
    """Thread ID should be the sender for stateless CLI."""
    connector = CodexCliConnector()
    sender = "+15551234567"

    thread_id = connector.get_or_create_thread(sender)
    assert thread_id == sender

    # Should return same ID for same sender
    thread_id2 = connector.get_or_create_thread(sender)
    assert thread_id2 == sender


def test_reset_thread_clears_context():
    """Reset thread should clear conversation context."""
    connector = CodexCliConnector()
    sender = "+15551234567"

    # Store some context
    connector._sender_contexts[sender] = ["User: hello\nAssistant: hi"]

    # Reset should clear it
    thread_id = connector.reset_thread(sender)
    assert thread_id == sender
    assert sender not in connector._sender_contexts


def test_shutdown_is_noop():
    """Shutdown is a no-op for CLI connector."""
    connector = CodexCliConnector()
    # Should not raise
    connector.shutdown()


def test_run_turn_success():
    """Test successful codex exec execution."""
    connector = CodexCliConnector(
        codex_command="codex",
        workspace="/tmp",
        timeout=30.0,
    )

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "This is a test response"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        response = connector.run_turn("+15551234567", "test prompt")

        # Verify subprocess was called correctly
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ["codex", "exec", "--skip-git-repo-check", "--yolo", "test prompt"]
        assert kwargs["cwd"] == "/tmp"
        assert kwargs["timeout"] == 30.0
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True

        # Verify response
        assert response == "This is a test response"


def test_run_turn_with_context():
    """Test that context is included in subsequent messages."""
    connector = CodexCliConnector(context_window=2)

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "Response 1"
    mock_result.stderr = ""

    sender = "+15551234567"

    with patch("subprocess.run", return_value=mock_result):
        # First turn - no context
        connector.run_turn(sender, "Message 1")

        mock_result.stdout = "Response 2"
        # Second turn - should include context
        connector.run_turn(sender, "Message 2")

        # Verify context was stored
        assert len(connector._sender_contexts[sender]) == 2
        assert "User: Message 1" in connector._sender_contexts[sender][0]
        assert "Assistant: Response 1" in connector._sender_contexts[sender][0]


def test_run_turn_timeout():
    """Test timeout handling."""
    connector = CodexCliConnector(timeout=1.0)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 1.0)):
        response = connector.run_turn("+15551234567", "test")

        assert "timed out" in response.lower()
        assert "1s" in response


def test_run_turn_command_not_found():
    """Test handling of missing codex binary."""
    connector = CodexCliConnector(codex_command="/nonexistent/codex")

    with patch("subprocess.run", side_effect=FileNotFoundError):
        response = connector.run_turn("+15551234567", "test")

        assert "not found" in response.lower()
        assert "/nonexistent/codex" in response


def test_run_turn_error_exit_code():
    """Test handling of non-zero exit codes."""
    connector = CodexCliConnector()

    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Something went wrong"

    with patch("subprocess.run", return_value=mock_result):
        response = connector.run_turn("+15551234567", "test")

        assert "Error" in response
        assert "exit code 1" in response


def test_run_turn_empty_response():
    """Test handling of empty response."""
    connector = CodexCliConnector()

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        response = connector.run_turn("+15551234567", "test")

        assert response == "No response generated."


def test_context_window_limiting():
    """Test that context is limited to configured window size."""
    connector = CodexCliConnector(context_window=2)

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    sender = "+15551234567"

    with patch("subprocess.run", return_value=mock_result):
        # Send 5 messages
        for i in range(5):
            mock_result.stdout = f"Response {i}"
            connector.run_turn(sender, f"Message {i}")

        # Should only keep last 4 (2x context_window)
        assert len(connector._sender_contexts[sender]) == 4
        # Most recent should be message 4
        assert "Message 4" in connector._sender_contexts[sender][-1]
        # Message 0 should not be in history
        assert not any("Message 0" in ctx for ctx in connector._sender_contexts[sender])
