"""Tests for CLI connector."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

from apple_flow.codex_cli_connector import CodexCliConnector


def _make_mock_proc(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    communicate_side_effect: Exception | None = None,
) -> Mock:
    proc = Mock()
    proc.pid = 12345
    proc.returncode = returncode
    proc.poll = Mock(return_value=returncode)
    proc.communicate = Mock(return_value=(stdout, stderr))
    if communicate_side_effect is not None:
        proc.communicate.side_effect = communicate_side_effect
    return proc


def test_cli_connector_implements_protocol():
    """Verify CLI connector implements ConnectorProtocol."""
    from apple_flow.protocols import ConnectorProtocol

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
        inject_tools_context=False,
    )

    mock_proc = _make_mock_proc(stdout="This is a test response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        response = connector.run_turn("+15551234567", "test prompt")

        # Verify subprocess was called correctly
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        assert args[0] == ["codex", "exec", "--skip-git-repo-check", "--yolo", "test prompt"]
        assert kwargs["cwd"] == "/tmp"
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.PIPE
        assert kwargs["text"] is True
        mock_proc.communicate.assert_called_once_with(timeout=30.0)

        # Verify response
        assert response == "This is a test response"


def test_run_turn_with_model_flag():
    """Test that -m flag is included when model is configured."""
    connector = CodexCliConnector(codex_command="codex", model="gpt-5.3-codex", inject_tools_context=False)

    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector.run_turn("+15551234567", "test prompt")

        args, _ = mock_popen.call_args
        assert args[0] == ["codex", "exec", "--skip-git-repo-check", "--yolo", "-m", "gpt-5.3-codex", "test prompt"]


def test_run_turn_sets_codex_config_path_from_options():
    connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector.run_turn(
            "+15551234567",
            "test prompt",
            options={"codex_config_path": "/tmp/team-preset.toml"},
        )

        _, kwargs = mock_popen.call_args
        env = kwargs["env"]
        assert env["CODEX_CONFIG_PATH"] == "/tmp/team-preset.toml"


def test_run_turn_no_model_flag_when_empty():
    """Test that -m flag is omitted when model is empty."""
    connector = CodexCliConnector(codex_command="codex", model="")

    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector.run_turn("+15551234567", "test prompt")

        args, _ = mock_popen.call_args
        assert "-m" not in args[0]


def test_run_turn_with_context():
    """Test that context is included in subsequent messages."""
    connector = CodexCliConnector(context_window=2)

    mock_proc = _make_mock_proc(stdout="Response 1")

    sender = "+15551234567"

    with patch("subprocess.Popen", return_value=mock_proc):
        # First turn - no context
        connector.run_turn(sender, "Message 1")

        mock_proc.communicate = Mock(return_value=("Response 2", ""))
        # Second turn - should include context
        connector.run_turn(sender, "Message 2")

        # Verify context was stored
        assert len(connector._sender_contexts[sender]) == 2
        assert "User: Message 1" in connector._sender_contexts[sender][0]
        assert "Assistant: Response 1" in connector._sender_contexts[sender][0]


def test_run_turn_timeout():
    """Test timeout handling."""
    connector = CodexCliConnector(timeout=1.0)

    timeout_proc = _make_mock_proc(
        communicate_side_effect=subprocess.TimeoutExpired("codex", 1.0)
    )
    with patch("subprocess.Popen", return_value=timeout_proc):
        response = connector.run_turn("+15551234567", "test")

        assert "timed out" in response.lower()
        assert "1s" in response


def test_run_turn_command_not_found():
    """Test handling of missing codex binary."""
    connector = CodexCliConnector(codex_command="/nonexistent/codex")

    with patch("subprocess.Popen", side_effect=FileNotFoundError):
        response = connector.run_turn("+15551234567", "test")

        assert "not found" in response.lower()
        assert "/nonexistent/codex" in response


def test_run_turn_error_exit_code():
    """Test handling of non-zero exit codes."""
    connector = CodexCliConnector()

    mock_proc = _make_mock_proc(returncode=1, stderr="Something went wrong")

    with patch("subprocess.Popen", return_value=mock_proc):
        response = connector.run_turn("+15551234567", "test")

        assert "Error" in response
        assert "exit code 1" in response


def test_run_turn_empty_response():
    """Test handling of empty response."""
    connector = CodexCliConnector()

    mock_proc = _make_mock_proc(stdout="")

    with patch("subprocess.Popen", return_value=mock_proc):
        response = connector.run_turn("+15551234567", "test")

        assert response == "No response generated."


def test_context_window_limiting():
    """Test that context is limited to configured window size."""
    connector = CodexCliConnector(context_window=2)

    mock_proc = _make_mock_proc()

    sender = "+15551234567"

    with patch("subprocess.Popen", return_value=mock_proc):
        # Send 5 messages
        for i in range(5):
            mock_proc.communicate = Mock(return_value=(f"Response {i}", ""))
            connector.run_turn(sender, f"Message {i}")

        # Should only keep last 4 (2x context_window)
        assert len(connector._sender_contexts[sender]) == 4
        # Most recent should be message 4
        assert "Message 4" in connector._sender_contexts[sender][-1]
        # Message 0 should not be in history
        assert not any("Message 0" in ctx for ctx in connector._sender_contexts[sender])


def test_run_turn_streaming_with_model_flag():
    """Test that run_turn_streaming includes -m flag when model is set."""
    connector = CodexCliConnector(codex_command="codex", model="gpt-5.3-codex")

    mock_proc = Mock()
    mock_proc.pid = 12345
    mock_proc.poll = Mock(return_value=0)
    mock_proc.stdout = iter(["line1\n", "line2\n"])
    mock_proc.returncode = 0
    mock_proc.stderr = Mock()

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        mock_proc.wait = Mock(return_value=0)
        connector.run_turn_streaming("+15551234567", "test prompt")

        args, _ = mock_popen.call_args
        assert "-m" in args[0]
        assert "gpt-5.3-codex" in args[0]


def test_run_turn_streaming_no_model_flag_when_empty():
    """Test that run_turn_streaming omits -m flag when model is empty."""
    connector = CodexCliConnector(codex_command="codex", model="")

    mock_proc = Mock()
    mock_proc.pid = 12345
    mock_proc.poll = Mock(return_value=0)
    mock_proc.stdout = iter(["response\n"])
    mock_proc.returncode = 0
    mock_proc.stderr = Mock()

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        mock_proc.wait = Mock(return_value=0)
        connector.run_turn_streaming("+15551234567", "test prompt")

        args, _ = mock_popen.call_args
        assert "-m" not in args[0]
