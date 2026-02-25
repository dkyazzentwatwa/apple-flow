"""Tests for Gemini CLI connector."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

from apple_flow.gemini_cli_connector import GeminiCliConnector


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
    mock_result = Mock(returncode=0, stdout="This is a test response", stderr="")

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        response = connector.run_turn("+15551234567", "test prompt")

        args, kwargs = mock_run.call_args
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
        assert kwargs["timeout"] == 30.0
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert response == "This is a test response"


def test_run_turn_includes_system_prompt_and_response_rules():
    connector = GeminiCliConnector(
        model="",
        inject_tools_context=False,
        system_prompt="You are concise.",
    )
    mock_result = Mock(returncode=0, stdout="ok", stderr="")

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        connector.run_turn("+15551234567", "say hi")
        args, _ = mock_run.call_args
        built_prompt = args[0][-1]
        assert "You are concise." in built_prompt
        assert "Response rules:" in built_prompt
        assert built_prompt.endswith("say hi")


def test_run_turn_no_model_flag_when_empty():
    connector = GeminiCliConnector(model="", inject_tools_context=False)
    mock_result = Mock(returncode=0, stdout="response", stderr="")

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        connector.run_turn("+15551234567", "test prompt")
        args, _ = mock_run.call_args
        assert "--model" not in args[0]
        assert "--approval-mode" in args[0]


def test_run_turn_no_approval_mode_when_empty():
    connector = GeminiCliConnector(model="", approval_mode="", inject_tools_context=False)
    mock_result = Mock(returncode=0, stdout="response", stderr="")

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        connector.run_turn("+15551234567", "test prompt")
        args, _ = mock_run.call_args
        assert "--approval-mode" not in args[0]


def test_run_turn_with_context():
    connector = GeminiCliConnector(context_window=2, inject_tools_context=False)
    mock_result = Mock(returncode=0, stdout="Response 1", stderr="")
    sender = "+15551234567"

    with patch("subprocess.run", return_value=mock_result):
        connector.run_turn(sender, "Message 1")
        mock_result.stdout = "Response 2"
        connector.run_turn(sender, "Message 2")

        assert len(connector._sender_contexts[sender]) == 2
        assert "User: Message 1" in connector._sender_contexts[sender][0]
        assert "Assistant: Response 1" in connector._sender_contexts[sender][0]


def test_run_turn_timeout():
    connector = GeminiCliConnector(timeout=1.0)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gemini", 1.0)):
        response = connector.run_turn("+15551234567", "test")
        assert "timed out" in response.lower()
        assert "1s" in response


def test_run_turn_command_not_found():
    connector = GeminiCliConnector(gemini_command="/nonexistent/gemini")

    with patch("subprocess.run", side_effect=FileNotFoundError):
        response = connector.run_turn("+15551234567", "test")
        assert "not found" in response.lower()
        assert "/nonexistent/gemini" in response


def test_run_turn_error_exit_code():
    connector = GeminiCliConnector()
    mock_result = Mock(returncode=1, stdout="", stderr="Something went wrong")

    with patch("subprocess.run", return_value=mock_result):
        response = connector.run_turn("+15551234567", "test")
        assert "Error" in response
        assert "exit code 1" in response


def test_run_turn_empty_response():
    connector = GeminiCliConnector()
    mock_result = Mock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", return_value=mock_result):
        response = connector.run_turn("+15551234567", "test")
        assert response == "No response generated."


def test_context_window_limiting():
    connector = GeminiCliConnector(context_window=2, inject_tools_context=False)
    mock_result = Mock(returncode=0, stderr="")
    sender = "+15551234567"

    with patch("subprocess.run", return_value=mock_result):
        for i in range(5):
            mock_result.stdout = f"Response {i}"
            connector.run_turn(sender, f"Message {i}")

        assert len(connector._sender_contexts[sender]) == 4
        assert "Message 4" in connector._sender_contexts[sender][-1]
        assert not any("Message 0" in ctx for ctx in connector._sender_contexts[sender])


def test_run_turn_streaming_with_model_flag():
    connector = GeminiCliConnector(gemini_command="gemini", model="gemini-3-flash-preview")

    mock_proc = Mock()
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
    mock_proc.stdout = iter(["response\n"])
    mock_proc.returncode = 0
    mock_proc.stderr = Mock()

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        mock_proc.wait = Mock(return_value=0)
        connector.run_turn_streaming("+15551234567", "test prompt")

        args, _ = mock_popen.call_args
        assert "--model" not in args[0]
