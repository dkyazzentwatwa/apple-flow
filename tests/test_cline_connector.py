"""Tests for Cline CLI connector."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from apple_flow.cline_connector import ClineConnector


def test_cline_connector_implements_protocol():
    """Verify Cline connector implements ConnectorProtocol."""
    from apple_flow.protocols import ConnectorProtocol

    connector = ClineConnector()
    assert isinstance(connector, ConnectorProtocol)


def test_ensure_started_is_noop():
    """ensure_started is a no-op for CLI connector."""
    connector = ClineConnector()
    connector.ensure_started()  # should not raise


def test_get_or_create_thread_returns_sender():
    """Thread ID is the sender for stateless CLI."""
    connector = ClineConnector()
    sender = "+15551234567"

    assert connector.get_or_create_thread(sender) == sender
    assert connector.get_or_create_thread(sender) == sender  # idempotent


def test_reset_thread_clears_context():
    """reset_thread clears conversation context."""
    connector = ClineConnector()
    sender = "+15551234567"

    connector._sender_contexts[sender] = ["User: hello\nAssistant: hi"]

    thread_id = connector.reset_thread(sender)
    assert thread_id == sender
    assert sender not in connector._sender_contexts


def test_shutdown_is_noop():
    """shutdown is a no-op for CLI connector."""
    connector = ClineConnector()
    connector.shutdown()  # should not raise


# ---------------------------------------------------------------------------
# _build_cmd
# ---------------------------------------------------------------------------

def test_build_cmd_defaults():
    """Default command includes -y and prompt."""
    connector = ClineConnector(use_json=False)
    cmd = connector._build_cmd("hello")
    assert cmd[0] == "cline"
    assert "-y" in cmd
    assert cmd[-1] == "hello"
    assert "--json" not in cmd
    assert "-m" not in cmd
    assert "-c" not in cmd


def test_build_cmd_with_json():
    """--json flag is included when use_json=True."""
    connector = ClineConnector(use_json=True)
    cmd = connector._build_cmd("hello")
    assert "--json" in cmd


def test_build_cmd_with_model():
    """-m flag included when model is set."""
    connector = ClineConnector(model="claude-sonnet-4-5-20250929", use_json=False)
    cmd = connector._build_cmd("hello")
    assert "-m" in cmd
    assert "claude-sonnet-4-5-20250929" in cmd


def test_build_cmd_no_model_flag_when_empty():
    """-m flag omitted when model is empty."""
    connector = ClineConnector(model="", use_json=False)
    cmd = connector._build_cmd("hello")
    assert "-m" not in cmd


def test_build_cmd_with_workspace():
    """-c flag included when workspace is set."""
    connector = ClineConnector(workspace="/tmp/myproject", use_json=False)
    cmd = connector._build_cmd("hello")
    assert "-c" in cmd
    assert "/tmp/myproject" in cmd


def test_build_cmd_with_timeout():
    """--timeout flag included when timeout > 0."""
    connector = ClineConnector(timeout=120.0, use_json=False)
    cmd = connector._build_cmd("hello")
    assert "--timeout" in cmd
    assert "120" in cmd


def test_build_cmd_full():
    """All flags combined correctly."""
    connector = ClineConnector(
        cline_command="/usr/local/bin/cline",
        workspace="/tmp/ws",
        timeout=60.0,
        model="gpt-4o",
        use_json=True,
    )
    cmd = connector._build_cmd("do something")
    assert cmd[0] == "/usr/local/bin/cline"
    assert "-y" in cmd
    assert "--json" in cmd
    assert "-m" in cmd
    assert "gpt-4o" in cmd
    assert "-c" in cmd
    assert "/tmp/ws" in cmd
    assert "--timeout" in cmd
    assert "60" in cmd
    assert cmd[-1] == "do something"


# ---------------------------------------------------------------------------
# _parse_json_output
# ---------------------------------------------------------------------------

def _ndjson(*objs: dict) -> str:
    return "\n".join(json.dumps(o) for o in objs)


def test_parse_json_output_extracts_final_say_text():
    """Returns the last non-partial say/text message when no completion_result."""
    raw = _ndjson(
        {"type": "say", "say": "text", "text": "I'm working on it...", "ts": 1},
        {"type": "say", "say": "text", "text": "Done! Here is the result.", "ts": 2},
    )
    connector = ClineConnector()
    assert connector._parse_json_output(raw) == "Done! Here is the result."


def test_parse_json_output_prefers_completion_result():
    """completion_result is preferred over intermediate say/text messages."""
    raw = _ndjson(
        {"type": "say", "say": "text", "text": "Searching emails...", "ts": 1},
        {"type": "say", "say": "text", "text": "Found 3 emails.", "ts": 2},
        {"type": "say", "say": "completion_result", "text": "Here are your 3 unread emails.", "ts": 3},
    )
    connector = ClineConnector()
    assert connector._parse_json_output(raw) == "Here are your 3 unread emails."


def test_parse_json_output_completion_result_no_text_parts():
    """completion_result works even when there are no say/text messages."""
    raw = _ndjson(
        {"type": "say", "say": "completion_result", "text": "hello from glm-5", "ts": 1},
    )
    connector = ClineConnector()
    assert connector._parse_json_output(raw) == "hello from glm-5"


def test_parse_json_output_skips_partial():
    """Partial streaming fragments are skipped."""
    raw = _ndjson(
        {"type": "say", "say": "text", "text": "partial chunk", "ts": 1, "partial": True},
        {"type": "say", "say": "text", "text": "Final answer.", "ts": 2, "partial": False},
    )
    connector = ClineConnector()
    assert connector._parse_json_output(raw) == "Final answer."


def test_parse_json_output_ignores_non_say_types():
    """Non-say message types are not included in the response."""
    raw = _ndjson(
        {"type": "ask", "say": "tool", "text": "Should I run this?", "ts": 1},
        {"type": "say", "say": "text", "text": "Task complete.", "ts": 2},
    )
    connector = ClineConnector()
    assert connector._parse_json_output(raw) == "Task complete."


def test_parse_json_output_ignores_non_text_say_subtypes():
    """say messages with say != 'text' are ignored."""
    raw = _ndjson(
        {"type": "say", "say": "tool_call", "text": "Running shell command", "ts": 1},
        {"type": "say", "say": "text", "text": "All done.", "ts": 2},
    )
    connector = ClineConnector()
    assert connector._parse_json_output(raw) == "All done."


def test_parse_json_output_empty_when_no_matches():
    """Returns empty string when no matching messages found."""
    raw = _ndjson(
        {"type": "ask", "say": "tool", "text": "tool call", "ts": 1},
    )
    connector = ClineConnector()
    assert connector._parse_json_output(raw) == ""


def test_parse_json_output_skips_invalid_lines():
    """Invalid JSON lines are skipped without error."""
    raw = "not json\n" + json.dumps({"type": "say", "say": "text", "text": "OK", "ts": 1})
    connector = ClineConnector()
    assert connector._parse_json_output(raw) == "OK"


def test_parse_json_output_empty_input():
    """Empty input returns empty string."""
    connector = ClineConnector()
    assert connector._parse_json_output("") == ""


# ---------------------------------------------------------------------------
# run_turn — subprocess mocking
# ---------------------------------------------------------------------------

def _make_mock_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> Mock:
    m = Mock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_run_turn_success_plain_text():
    """Successful plain-text run returns stdout."""
    connector = ClineConnector(cline_command="cline", workspace="/tmp", timeout=30.0, use_json=False)
    mock_result = _make_mock_result(stdout="Task complete.")

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        response = connector.run_turn("+15551234567", "do the thing")

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0][0] == "cline"
        assert "-y" in args[0]
        assert kwargs["cwd"] == "/tmp"
        assert kwargs["timeout"] == 30.0
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert response == "Task complete."


def test_run_turn_success_json_mode():
    """JSON mode parses NDJSON output correctly."""
    connector = ClineConnector(use_json=True)
    ndjson_output = _ndjson(
        {"type": "say", "say": "text", "text": "Here is your answer.", "ts": 1},
    )
    mock_result = _make_mock_result(stdout=ndjson_output)

    with patch("subprocess.run", return_value=mock_result):
        response = connector.run_turn("+15551234567", "test")
        assert response == "Here is your answer."


def test_run_turn_with_model_flag():
    """-m flag is passed when model is configured."""
    connector = ClineConnector(model="gpt-4o", use_json=False)
    mock_result = _make_mock_result(stdout="response")

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        connector.run_turn("+15551234567", "test")
        args, _ = mock_run.call_args
        assert "-m" in args[0]
        assert "gpt-4o" in args[0]


def test_run_turn_with_context():
    """Second turn includes context from first turn in the prompt."""
    connector = ClineConnector(context_window=2, use_json=False)
    sender = "+15551234567"

    mock_result = _make_mock_result(stdout="Response 1")
    with patch("subprocess.run", return_value=mock_result):
        connector.run_turn(sender, "Message 1")

    mock_result.stdout = "Response 2"
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        connector.run_turn(sender, "Message 2")
        args, _ = mock_run.call_args
        prompt_arg = args[0][-1]
        assert "Previous conversation context" in prompt_arg
        assert "Message 1" in prompt_arg
        assert "Response 1" in prompt_arg

    assert len(connector._sender_contexts[sender]) == 2


def test_run_turn_empty_response_fallback():
    """Empty response falls back to 'No response generated.'"""
    connector = ClineConnector(use_json=False)
    mock_result = _make_mock_result(stdout="   ")

    with patch("subprocess.run", return_value=mock_result):
        response = connector.run_turn("+15551234567", "test")
        assert response == "No response generated."


def test_run_turn_error_exit_code():
    """Non-zero exit code returns an error string."""
    connector = ClineConnector()
    mock_result = _make_mock_result(returncode=1, stderr="Something went wrong")

    with patch("subprocess.run", return_value=mock_result):
        response = connector.run_turn("+15551234567", "test")
        assert "Error" in response
        assert "exit code 1" in response


def test_run_turn_timeout():
    """TimeoutExpired returns a timeout error message."""
    connector = ClineConnector(timeout=5.0, use_json=False)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cline", 5.0)):
        response = connector.run_turn("+15551234567", "test")
        assert "timed out" in response.lower()
        assert "5s" in response


def test_run_turn_binary_not_found():
    """FileNotFoundError returns an install hint."""
    connector = ClineConnector(cline_command="/nonexistent/cline")

    with patch("subprocess.run", side_effect=FileNotFoundError):
        response = connector.run_turn("+15551234567", "test")
        assert "not found" in response.lower()
        assert "npm install -g cline" in response


def test_run_turn_unexpected_error():
    """Unexpected exceptions are caught and reported."""
    connector = ClineConnector()

    with patch("subprocess.run", side_effect=RuntimeError("boom")):
        response = connector.run_turn("+15551234567", "test")
        assert "RuntimeError" in response
        assert "boom" in response


# ---------------------------------------------------------------------------
# Context window limiting
# ---------------------------------------------------------------------------

def test_context_window_limiting():
    """History is pruned to 2x context_window entries."""
    connector = ClineConnector(context_window=2, use_json=False)
    sender = "+15551234567"
    mock_result = _make_mock_result(stdout="ok")

    with patch("subprocess.run", return_value=mock_result):
        for i in range(5):
            mock_result.stdout = f"Response {i}"
            connector.run_turn(sender, f"Message {i}")

    # max_history = context_window * 2 = 4
    assert len(connector._sender_contexts[sender]) == 4
    assert "Message 4" in connector._sender_contexts[sender][-1]
    assert not any("Message 0" in ctx for ctx in connector._sender_contexts[sender])


# ---------------------------------------------------------------------------
# run_turn_streaming
# ---------------------------------------------------------------------------

def test_run_turn_streaming_plain_text():
    """Streaming collects lines and returns joined output."""
    connector = ClineConnector(use_json=False)

    mock_proc = Mock()
    mock_proc.stdout = iter(["line one\n", "line two\n"])
    mock_proc.returncode = 0
    mock_proc.stderr = Mock()
    mock_proc.wait = Mock(return_value=0)

    with patch("subprocess.Popen", return_value=mock_proc):
        response = connector.run_turn_streaming("+15551234567", "test")
        assert "line one" in response
        assert "line two" in response


def test_run_turn_streaming_calls_on_progress():
    """on_progress callback is called for each output line in plain text mode."""
    connector = ClineConnector(use_json=False)
    progress_calls: list[str] = []

    mock_proc = Mock()
    mock_proc.stdout = iter(["chunk 1\n", "chunk 2\n"])
    mock_proc.returncode = 0
    mock_proc.stderr = Mock()
    mock_proc.wait = Mock(return_value=0)

    with patch("subprocess.Popen", return_value=mock_proc):
        connector.run_turn_streaming("+15551234567", "test", on_progress=progress_calls.append)

    assert "chunk 1\n" in progress_calls
    assert "chunk 2\n" in progress_calls


def test_run_turn_streaming_json_on_progress():
    """on_progress receives extracted text from JSON lines."""
    connector = ClineConnector(use_json=True)
    progress_texts: list[str] = []

    json_line = json.dumps({"type": "say", "say": "text", "text": "step done", "ts": 1}) + "\n"

    mock_proc = Mock()
    mock_proc.stdout = iter([json_line])
    mock_proc.returncode = 0
    mock_proc.stderr = Mock()
    mock_proc.wait = Mock(return_value=0)

    with patch("subprocess.Popen", return_value=mock_proc):
        connector.run_turn_streaming("+15551234567", "test", on_progress=progress_texts.append)

    assert "step done" in progress_texts


def test_run_turn_streaming_error_falls_back_to_run_turn():
    """Exception during streaming falls back to regular run_turn."""
    connector = ClineConnector(use_json=False)

    with patch("subprocess.Popen", side_effect=OSError("fail")):
        with patch.object(connector, "run_turn", return_value="fallback") as mock_rt:
            response = connector.run_turn_streaming("+15551234567", "test")
            mock_rt.assert_called_once()
            assert response == "fallback"
