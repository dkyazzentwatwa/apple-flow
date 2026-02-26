"""Tests for Gemini CLI connector."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

from apple_flow.gemini_cli_connector import GeminiCliConnector


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


def test_gemini_cli_connector_implements_protocol():
    """Verify Gemini connector implements ConnectorProtocol."""
    from apple_flow.protocols import ConnectorProtocol

    connector = GeminiCliConnector()
    assert isinstance(connector, ConnectorProtocol)


def test_ensure_started_is_noop():
    connector = GeminiCliConnector()
    connector.ensure_started()


def test_get_or_create_thread_returns_sender():
    connector = GeminiCliConnector()
    sender = "+15551234567"

    assert connector.get_or_create_thread(sender) == sender
    assert connector.get_or_create_thread(sender) == sender


def test_reset_thread_clears_context():
    connector = GeminiCliConnector()
    sender = "+15551234567"
    connector._sender_contexts[sender] = ["User: hello\nAssistant: hi"]

    assert connector.reset_thread(sender) == sender
    assert sender not in connector._sender_contexts


def test_shutdown_is_noop():
    connector = GeminiCliConnector()
    connector.shutdown()


def test_run_turn_success():
    connector = GeminiCliConnector(
        gemini_command="gemini",
        workspace="/tmp",
        timeout=30.0,
        model="gemini-3-flash-preview",
        inject_tools_context=False,
    )
    mock_proc = _make_mock_proc(stdout="This is a test response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        response = connector.run_turn("+15551234567", "test prompt")

        args, kwargs = mock_popen.call_args
        assert args[0][:6] == [
            "gemini",
            "--model",
            "gemini-3-flash-preview",
            "--approval-mode",
            "yolo",
            "-p",
        ]
        assert args[0][6].endswith("test prompt")
        assert kwargs["cwd"] == "/tmp"
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.PIPE
        assert kwargs["text"] is True
        mock_proc.communicate.assert_called_once_with(timeout=30.0)
        assert response == "This is a test response"


def test_run_turn_includes_system_prompt_and_response_rules():
    connector = GeminiCliConnector(
        model="",
        inject_tools_context=False,
        system_prompt="You are concise.",
    )
    mock_proc = _make_mock_proc(stdout="ok")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector.run_turn("+15551234567", "say hi")
        args, _ = mock_popen.call_args
        built_prompt = args[0][-1]
        assert "You are concise." in built_prompt
        assert "Response rules:" in built_prompt
        assert built_prompt.endswith("say hi")


def test_run_turn_no_model_flag_when_empty():
    connector = GeminiCliConnector(model="", inject_tools_context=False)
    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector.run_turn("+15551234567", "test prompt")
        args, _ = mock_popen.call_args
        assert "--model" not in args[0]
        assert "--approval-mode" in args[0]


def test_run_turn_no_approval_mode_when_empty():
    connector = GeminiCliConnector(model="", approval_mode="", inject_tools_context=False)
    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector.run_turn("+15551234567", "test prompt")
        args, _ = mock_popen.call_args
        assert "--approval-mode" not in args[0]


def test_run_turn_with_valid_approval_mode():
    connector = GeminiCliConnector(model="", approval_mode="plan", inject_tools_context=False)
    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector.run_turn("+15551234567", "test prompt")
        args, _ = mock_popen.call_args
        assert "--approval-mode" in args[0]
        mode_idx = args[0].index("--approval-mode")
        assert args[0][mode_idx + 1] == "plan"


def test_invalid_approval_mode_falls_back_to_yolo(caplog):
    caplog.set_level("WARNING")
    connector = GeminiCliConnector(model="", approval_mode="INVALID_MODE", inject_tools_context=False)
    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector.run_turn("+15551234567", "test prompt")
        args, _ = mock_popen.call_args
        mode_idx = args[0].index("--approval-mode")
        assert args[0][mode_idx + 1] == "yolo"

    assert "Invalid Gemini approval mode" in caplog.text


def test_run_turn_with_context():
    connector = GeminiCliConnector(context_window=2, inject_tools_context=False)
    mock_proc = _make_mock_proc(stdout="Response 1")
    sender = "+15551234567"

    with patch("subprocess.Popen", return_value=mock_proc):
        connector.run_turn(sender, "Message 1")
        mock_proc.communicate = Mock(return_value=("Response 2", ""))
        connector.run_turn(sender, "Message 2")

        assert len(connector._sender_contexts[sender]) == 2
        assert "User: Message 1" in connector._sender_contexts[sender][0]
        assert "Assistant: Response 1" in connector._sender_contexts[sender][0]


def test_run_turn_timeout():
    connector = GeminiCliConnector(timeout=1.0)

    timeout_proc = _make_mock_proc(
        communicate_side_effect=subprocess.TimeoutExpired("gemini", 1.0)
    )
    with patch("subprocess.Popen", return_value=timeout_proc):
        response = connector.run_turn("+15551234567", "test")
        assert "timed out" in response.lower()
        assert "1s" in response


def test_run_turn_command_not_found():
    connector = GeminiCliConnector(gemini_command="/nonexistent/gemini")

    with patch("subprocess.Popen", side_effect=FileNotFoundError):
        response = connector.run_turn("+15551234567", "test")
        assert "not found" in response.lower()
        assert "/nonexistent/gemini" in response


def test_run_turn_error_exit_code():
    connector = GeminiCliConnector()
    mock_proc = _make_mock_proc(returncode=1, stderr="Something went wrong")

    with patch("subprocess.Popen", return_value=mock_proc):
        response = connector.run_turn("+15551234567", "test")
        assert "Error" in response
        assert "exit code 1" in response


def test_run_turn_empty_response():
    connector = GeminiCliConnector()
    mock_proc = _make_mock_proc(stdout="")

    with patch("subprocess.Popen", return_value=mock_proc):
        response = connector.run_turn("+15551234567", "test")
        assert response == "No response generated."


def test_context_window_limiting():
    connector = GeminiCliConnector(context_window=2, inject_tools_context=False)
    mock_proc = _make_mock_proc()
    sender = "+15551234567"

    with patch("subprocess.Popen", return_value=mock_proc):
        for i in range(5):
            mock_proc.communicate = Mock(return_value=(f"Response {i}", ""))
            connector.run_turn(sender, f"Message {i}")

        assert len(connector._sender_contexts[sender]) == 4
        assert "Message 4" in connector._sender_contexts[sender][-1]
        assert not any("Message 0" in ctx for ctx in connector._sender_contexts[sender])


def test_run_turn_streaming_with_model_flag():
    connector = GeminiCliConnector(gemini_command="gemini", model="gemini-3-flash-preview")

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
        assert "--model" in args[0]
        assert "gemini-3-flash-preview" in args[0]


def test_run_turn_streaming_no_model_flag_when_empty():
    connector = GeminiCliConnector(gemini_command="gemini", model="")

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
        assert "--model" not in args[0]
