"""Tests for Kilo CLI connector."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

from apple_flow.kilo_cli_connector import KiloCliConnector


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
    proc.stdin = Mock()
    if communicate_side_effect is not None:
        proc.communicate.side_effect = communicate_side_effect
    return proc


def test_kilo_cli_connector_implements_protocol():
    """Verify Kilo CLI connector implements ConnectorProtocol."""
    from apple_flow.protocols import ConnectorProtocol

    connector = KiloCliConnector()
    assert isinstance(connector, ConnectorProtocol)


def test_ensure_started_is_noop():
    """Ensure started is a no-op for Kilo CLI connector."""
    connector = KiloCliConnector()
    # Should not raise
    connector.ensure_started()


def test_get_or_create_thread_returns_sender():
    """Thread ID should be the sender for stateless Kilo CLI."""
    connector = KiloCliConnector()
    sender = "+15551234567"

    thread_id = connector.get_or_create_thread(sender)
    assert thread_id == sender


def test_reset_thread_clears_context():
    """Reset thread should clear conversation context."""
    connector = KiloCliConnector()
    sender = "+15551234567"

    # Store some context
    connector._sender_contexts[sender] = ["User: hello\nAssistant: hi"]

    # Reset should clear it
    thread_id = connector.reset_thread(sender)
    assert thread_id == sender
    assert sender not in connector._sender_contexts


def test_run_turn_success():
    """Test successful kilo run execution."""
    connector = KiloCliConnector(
        kilo_command="kilo",
        workspace="/tmp",
        timeout=30.0,
        inject_tools_context=False,
    )

    mock_proc = _make_mock_proc(stdout="This is a Kilo response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        response = connector.run_turn("+15551234567", "test prompt")

        # Verify subprocess was called correctly
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        assert args[0] == ["kilo", "run", "--auto"]
        assert kwargs["cwd"] == "/tmp"
        assert kwargs["stdin"] == subprocess.PIPE
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.PIPE
        assert kwargs["text"] is True

        # Verify prompt payload includes the user prompt (connector may prepend rules)
        mock_proc.communicate.assert_called_once()
        _, call_kwargs = mock_proc.communicate.call_args
        sent_input = call_kwargs["input"]
        assert call_kwargs["timeout"] == 30.0
        assert sent_input.endswith("test prompt")

        # Verify response
        assert response == "This is a Kilo response"


def test_run_turn_with_model_flag():
    """Test that --model flag is included when model is configured."""
    connector = KiloCliConnector(kilo_command="kilo", model="gemini-3-flash-preview", inject_tools_context=False)

    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector.run_turn("+15551234567", "test prompt")

        args, _ = mock_popen.call_args
        assert args[0] == ["kilo", "run", "--auto", "--model", "gemini-3-flash-preview"]


def test_run_turn_timeout():
    """Test timeout handling."""
    connector = KiloCliConnector(timeout=1.0)

    timeout_proc = _make_mock_proc(
        communicate_side_effect=subprocess.TimeoutExpired("kilo", 1.0)
    )
    with patch("subprocess.Popen", return_value=timeout_proc):
        response = connector.run_turn("+15551234567", "test")

        assert "timed out" in response.lower()
        assert "1s" in response


def test_run_turn_error_exit_code():
    """Test handling of non-zero exit codes."""
    connector = KiloCliConnector()

    mock_proc = _make_mock_proc(returncode=1, stderr="Something went wrong")

    with patch("subprocess.Popen", return_value=mock_proc):
        response = connector.run_turn("+15551234567", "test")

        assert "Error" in response
        assert "exit code 1" in response


def test_run_turn_streaming_success():
    """Test successful kilo run streaming execution."""
    connector = KiloCliConnector(timeout=30.0)

    mock_proc = Mock()
    mock_proc.pid = 12345
    mock_proc.returncode = 0
    mock_proc.stdin = Mock()
    mock_proc.stdout = iter(["Response ", "line 1\n", "line 2"])
    mock_proc.stderr = Mock()
    mock_proc.wait = Mock(return_value=0)

    with patch("subprocess.Popen", return_value=mock_proc):
        progress_lines = []
        def on_progress(line):
            progress_lines.append(line)

        response = connector.run_turn_streaming("+15551234567", "test prompt", on_progress=on_progress)

        assert response == "Response line 1\nline 2"
        assert len(progress_lines) == 3
        assert progress_lines[0] == "Response "
        mock_proc.stdin.write.assert_called_once()
        mock_proc.stdin.close.assert_called_once()
