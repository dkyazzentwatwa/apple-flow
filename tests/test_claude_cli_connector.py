"""Tests for Claude CLI connector."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

from apple_flow.claude_cli_connector import ClaudeCliConnector


def test_claude_cli_connector_implements_protocol():
    """Verify Claude CLI connector implements ConnectorProtocol."""
    from apple_flow.protocols import ConnectorProtocol

    connector = ClaudeCliConnector()
    assert isinstance(connector, ConnectorProtocol)


def test_ensure_started_is_noop():
    """Ensure started is a no-op for Claude CLI connector."""
    connector = ClaudeCliConnector()
    # Should not raise
    connector.ensure_started()


def test_get_or_create_thread_returns_sender():
    """Thread ID should be the sender for stateless Claude CLI."""
    connector = ClaudeCliConnector()
    sender = "+15551234567"

    thread_id = connector.get_or_create_thread(sender)
    assert thread_id == sender

    # Should return same ID for same sender
    thread_id2 = connector.get_or_create_thread(sender)
    assert thread_id2 == sender


def test_reset_thread_clears_context():
    """Reset thread should clear conversation context."""
    connector = ClaudeCliConnector()
    sender = "+15551234567"

    # Store some context
    connector._sender_contexts[sender] = ["User: hello\nAssistant: hi"]

    # Reset should clear it
    thread_id = connector.reset_thread(sender)
    assert thread_id == sender
    assert sender not in connector._sender_contexts


def test_shutdown_is_noop():
    """Shutdown is a no-op for Claude CLI connector."""
    connector = ClaudeCliConnector()
    # Should not raise
    connector.shutdown()


def test_run_turn_success():
    """Test successful claude exec with --dangerously-skip-permissions."""
    connector = ClaudeCliConnector(
        claude_command="claude",
        workspace="/tmp",
        timeout=30.0,
        inject_tools_context=False,
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
        assert args[0] == ["claude", "--dangerously-skip-permissions", "-p", "test prompt"]
        assert kwargs["cwd"] == "/tmp"
        assert kwargs["timeout"] == 30.0
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True

        # Verify response
        assert response == "This is a test response"


def test_run_turn_without_skip_permissions():
    """Test that --dangerously-skip-permissions flag is absent when disabled."""
    connector = ClaudeCliConnector(
        claude_command="claude",
        dangerously_skip_permissions=False,
        inject_tools_context=False,
    )

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "response"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        connector.run_turn("+15551234567", "test prompt")

        args, _ = mock_run.call_args
        assert "--dangerously-skip-permissions" not in args[0]
        assert args[0] == ["claude", "-p", "test prompt"]


def test_run_turn_with_model_flag():
    """Test that --model flag is included when model is configured."""
    connector = ClaudeCliConnector(claude_command="claude", model="claude-sonnet-4-6", inject_tools_context=False)

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "response"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        connector.run_turn("+15551234567", "test prompt")

        args, _ = mock_run.call_args
        assert args[0] == [
            "claude",
            "--dangerously-skip-permissions",
            "--model",
            "claude-sonnet-4-6",
            "-p",
            "test prompt",
        ]


def test_run_turn_no_model_flag_when_empty():
    """Test that --model flag is omitted when model is empty."""
    connector = ClaudeCliConnector(claude_command="claude", model="")

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "response"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        connector.run_turn("+15551234567", "test prompt")

        args, _ = mock_run.call_args
        assert "--model" not in args[0]


def test_run_turn_with_tools_flags():
    """Test that --tools and --allowedTools are included when configured."""
    connector = ClaudeCliConnector(
        claude_command="claude",
        tools=["default", "WebSearch"],
        allowed_tools=["WebSearch"],
    )

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "response"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        connector.run_turn("+15551234567", "test prompt")

        args, _ = mock_run.call_args
        assert "--tools" in args[0]
        assert "default,WebSearch" in args[0]
        assert "--allowedTools" in args[0]
        assert "WebSearch" in args[0]


def test_run_turn_with_context():
    """Test that context is included in subsequent messages."""
    connector = ClaudeCliConnector(context_window=2)

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
    connector = ClaudeCliConnector(timeout=1.0)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 1.0)):
        response = connector.run_turn("+15551234567", "test")

        assert "timed out" in response.lower()
        assert "1s" in response


def test_run_turn_command_not_found():
    """Test handling of missing claude binary."""
    connector = ClaudeCliConnector(claude_command="/nonexistent/claude")

    with patch("subprocess.run", side_effect=FileNotFoundError):
        response = connector.run_turn("+15551234567", "test")

        assert "not found" in response.lower()
        assert "/nonexistent/claude" in response


def test_run_turn_error_exit_code():
    """Test handling of non-zero exit codes."""
    connector = ClaudeCliConnector()

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
    connector = ClaudeCliConnector()

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        response = connector.run_turn("+15551234567", "test")

        assert response == "No response generated."


def test_context_window_limiting():
    """Test that context is limited to configured window size."""
    connector = ClaudeCliConnector(context_window=2)

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


def test_run_turn_streaming_with_model_flag():
    """Test that run_turn_streaming includes --model flag when model is set."""
    connector = ClaudeCliConnector(claude_command="claude", model="claude-sonnet-4-6")

    mock_proc = Mock()
    mock_proc.stdout = iter(["line1\n", "line2\n"])
    mock_proc.returncode = 0
    mock_proc.stderr = Mock()

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        mock_proc.wait = Mock(return_value=0)
        connector.run_turn_streaming("+15551234567", "test prompt")

        args, _ = mock_popen.call_args
        assert "--model" in args[0]
        assert "claude-sonnet-4-6" in args[0]


def test_run_turn_streaming_no_model_flag_when_empty():
    """Test that run_turn_streaming omits --model flag when model is empty."""
    connector = ClaudeCliConnector(claude_command="claude", model="")

    mock_proc = Mock()
    mock_proc.stdout = iter(["response\n"])
    mock_proc.returncode = 0
    mock_proc.stderr = Mock()

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        mock_proc.wait = Mock(return_value=0)
        connector.run_turn_streaming("+15551234567", "test prompt")

        args, _ = mock_popen.call_args
        assert "--model" not in args[0]
