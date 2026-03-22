"""Tests for CodexCliConnector."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest

from apple_flow.codex_cli_connector import CodexCliConnector


def _make_mock_proc(
    *,
    returncode: int = 0,
    stdout: str = "response text",
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


# --- __init__ ---

def test_init_defaults():
    connector = CodexCliConnector()
    assert connector.codex_command == "codex"
    assert connector.timeout == 300.0
    assert connector.context_window == 3
    assert connector.model == ""
    assert connector.inject_tools_context is True
    assert connector.workspace is None
    assert connector.soul_prompt == ""


def test_init_custom():
    connector = CodexCliConnector(
        codex_command="/usr/local/bin/codex",
        workspace="/home/user/project",
        timeout=60.0,
        context_window=5,
        model="gpt-4",
        inject_tools_context=False,
    )
    assert connector.codex_command == "/usr/local/bin/codex"
    assert connector.workspace == "/home/user/project"
    assert connector.timeout == 60.0
    assert connector.context_window == 5
    assert connector.model == "gpt-4"
    assert connector.inject_tools_context is False


# --- set_soul_prompt ---

def test_set_soul_prompt():
    connector = CodexCliConnector()
    connector.set_soul_prompt("  You are a helpful assistant.  ")
    assert connector.soul_prompt == "You are a helpful assistant."


def test_set_soul_prompt_empty():
    connector = CodexCliConnector()
    connector.set_soul_prompt("")
    assert connector.soul_prompt == ""


# --- ensure_started ---

def test_ensure_started_is_noop():
    connector = CodexCliConnector()
    connector.ensure_started()  # Should not raise


# --- get_or_create_thread ---

def test_get_or_create_thread_returns_sender():
    connector = CodexCliConnector()
    sender = "+15551234567"
    assert connector.get_or_create_thread(sender) == sender


def test_get_or_create_thread_idempotent():
    connector = CodexCliConnector()
    sender = "+15551234567"
    t1 = connector.get_or_create_thread(sender)
    t2 = connector.get_or_create_thread(sender)
    assert t1 == t2 == sender


# --- reset_thread ---

def test_reset_thread_clears_context():
    connector = CodexCliConnector()
    sender = "+15551234567"
    connector._sender_contexts[sender] = ["User: hi\nAssistant: hello"]

    result = connector.reset_thread(sender)
    assert result == sender
    assert sender not in connector._sender_contexts


def test_reset_thread_no_context_is_safe():
    connector = CodexCliConnector()
    sender = "+15551234567"
    result = connector.reset_thread(sender)
    assert result == sender


# --- shutdown ---

def test_shutdown_is_noop():
    connector = CodexCliConnector()
    connector.shutdown()  # Should not raise


# --- cancel_active_processes ---

def test_cancel_active_processes_no_processes():
    connector = CodexCliConnector()
    count = connector.cancel_active_processes()
    assert count == 0


def test_cancel_active_processes_with_thread_id():
    connector = CodexCliConnector()
    count = connector.cancel_active_processes(thread_id="+15551234567")
    assert count == 0


# --- run_turn success ---

def test_run_turn_success():
    mock_proc = _make_mock_proc(stdout="codex output here")

    with patch("subprocess.Popen", return_value=mock_proc):
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        result = connector.run_turn("+15551234567", "do something")

    assert result == "codex output here"


def test_run_turn_stores_exchange():
    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc):
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        connector.run_turn("+15551234567", "hello")

    assert "+15551234567" in connector._sender_contexts
    assert len(connector._sender_contexts["+15551234567"]) == 1
    assert "User: hello" in connector._sender_contexts["+15551234567"][0]
    assert "Assistant: response" in connector._sender_contexts["+15551234567"][0]


def test_run_turn_with_model():
    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector = CodexCliConnector(codex_command="codex", model="gpt-4", inject_tools_context=False)
        connector.run_turn("+15551234567", "hello")

    call_args = mock_popen.call_args[0][0]
    assert "-m" in call_args
    assert "gpt-4" in call_args


def test_run_turn_nonzero_returncode():
    mock_proc = _make_mock_proc(returncode=1, stdout="", stderr="codex crashed")

    with patch("subprocess.Popen", return_value=mock_proc):
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        result = connector.run_turn("+15551234567", "hello")

    assert "Error" in result
    assert "exit code 1" in result


def test_run_turn_empty_response():
    mock_proc = _make_mock_proc(stdout="   ")

    with patch("subprocess.Popen", return_value=mock_proc):
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        result = connector.run_turn("+15551234567", "hello")

    assert result == "No response generated."


def test_run_turn_timeout():
    mock_proc = _make_mock_proc(communicate_side_effect=subprocess.TimeoutExpired("codex", 300))

    with patch("subprocess.Popen", return_value=mock_proc):
        connector = CodexCliConnector(codex_command="codex", timeout=300.0, inject_tools_context=False)
        result = connector.run_turn("+15551234567", "hello")

    assert "timed out" in result.lower()
    assert "300" in result


def test_run_turn_binary_not_found():
    with patch("subprocess.Popen", side_effect=FileNotFoundError):
        connector = CodexCliConnector(codex_command="nonexistent-codex", inject_tools_context=False)
        result = connector.run_turn("+15551234567", "hello")

    assert "not found" in result.lower()


def test_run_turn_unexpected_exception():
    with patch("subprocess.Popen", side_effect=RuntimeError("unexpected")):
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        result = connector.run_turn("+15551234567", "hello")

    assert "RuntimeError" in result


def test_run_turn_with_codex_config_path():
    mock_proc = _make_mock_proc(stdout="response")

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        connector.run_turn("+15551234567", "hello", options={"codex_config_path": "/tmp/config.json"})

    call_kwargs = mock_popen.call_args[1]
    assert call_kwargs["env"].get("CODEX_CONFIG_PATH") == "/tmp/config.json"


# --- run_turn_streaming ---

def test_run_turn_streaming_success():
    from unittest.mock import patch as _patch

    progress_calls: list[str] = []

    fake_capture = MagicMock()
    fake_capture.returncode = 0
    fake_capture.stdout = "streamed response"
    fake_capture.stderr = ""

    mock_proc = Mock()
    mock_proc.pid = 123
    mock_proc.returncode = 0

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("apple_flow.codex_cli_connector.capture_subprocess_streams", return_value=fake_capture):
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        result = connector.run_turn_streaming(
            "+15551234567", "hello", on_progress=progress_calls.append
        )

    assert result == "streamed response"


def test_run_turn_streaming_nonzero_returncode():
    fake_capture = MagicMock()
    fake_capture.returncode = 1
    fake_capture.stdout = ""
    fake_capture.stderr = "failed"

    mock_proc = Mock()
    mock_proc.pid = 123
    mock_proc.returncode = 1

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("apple_flow.codex_cli_connector.capture_subprocess_streams", return_value=fake_capture):
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        result = connector.run_turn_streaming("+15551234567", "hello")

    assert "Error" in result
    assert "exit code 1" in result


def test_run_turn_streaming_empty_response():
    fake_capture = MagicMock()
    fake_capture.returncode = 0
    fake_capture.stdout = "  "
    fake_capture.stderr = ""

    mock_proc = Mock()
    mock_proc.pid = 123

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("apple_flow.codex_cli_connector.capture_subprocess_streams", return_value=fake_capture):
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        result = connector.run_turn_streaming("+15551234567", "hello")

    assert result == "No response generated."


def test_run_turn_streaming_exception_falls_back_to_run_turn():
    mock_proc = Mock()
    mock_proc.pid = 123
    mock_proc.returncode = 0
    mock_proc.communicate = Mock(return_value=("fallback response", ""))

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("apple_flow.codex_cli_connector.capture_subprocess_streams", side_effect=RuntimeError("stream err")):
        connector = CodexCliConnector(codex_command="codex", inject_tools_context=False)
        result = connector.run_turn_streaming("+15551234567", "hello")

    # Falls back to run_turn which uses communicate
    assert result == "fallback response"


# --- _build_prompt_with_context ---

def test_build_prompt_no_history_no_tools_context():
    connector = CodexCliConnector(inject_tools_context=False)
    prompt = connector._build_prompt_with_context("+15551234567", "hello world")
    assert prompt == "hello world"


def test_build_prompt_with_soul():
    connector = CodexCliConnector(inject_tools_context=False)
    connector.set_soul_prompt("You are helpful.")
    prompt = connector._build_prompt_with_context("+15551234567", "hello")
    assert prompt.startswith("You are helpful.")
    assert "New message:\nhello" in prompt


def test_build_prompt_with_history():
    connector = CodexCliConnector(context_window=2, inject_tools_context=False)
    connector._sender_contexts["+15551234567"] = [
        "User: a\nAssistant: b",
        "User: c\nAssistant: d",
    ]
    prompt = connector._build_prompt_with_context("+15551234567", "new message")
    assert "Previous conversation context:" in prompt
    assert "User: a" in prompt
    assert "New message:\nnew message" in prompt


def test_build_prompt_context_window_limits_history():
    connector = CodexCliConnector(context_window=1, inject_tools_context=False)
    connector._sender_contexts["+15551234567"] = [
        "User: old\nAssistant: old reply",
        "User: recent\nAssistant: recent reply",
    ]
    prompt = connector._build_prompt_with_context("+15551234567", "new")
    # Only most recent 1 item in context window
    assert "recent" in prompt
    # Old item should NOT appear (context_window=1)
    assert "User: old\nAssistant: old reply" not in prompt


def test_build_prompt_with_tools_context():
    connector = CodexCliConnector(inject_tools_context=True)
    prompt = connector._build_prompt_with_context("+15551234567", "hello")
    # TOOLS_CONTEXT should be included
    from apple_flow.apple_tools import TOOLS_CONTEXT
    assert TOOLS_CONTEXT in prompt


# --- _store_exchange ---

def test_store_exchange_creates_entry():
    connector = CodexCliConnector()
    connector._store_exchange("+15551234567", "user msg", "assistant reply")
    assert "+15551234567" in connector._sender_contexts
    assert connector._sender_contexts["+15551234567"][0] == "User: user msg\nAssistant: assistant reply"


def test_store_exchange_caps_at_max_history():
    connector = CodexCliConnector(context_window=2)
    sender = "+15551234567"
    max_history = connector.context_window * 2  # 4

    # Add 5 entries (exceeds max)
    for i in range(5):
        connector._store_exchange(sender, f"msg {i}", f"reply {i}")

    assert len(connector._sender_contexts[sender]) == max_history


def test_store_exchange_multiple_senders():
    connector = CodexCliConnector()
    connector._store_exchange("+1111", "a", "b")
    connector._store_exchange("+2222", "c", "d")
    assert "+1111" in connector._sender_contexts
    assert "+2222" in connector._sender_contexts
    assert len(connector._sender_contexts["+1111"]) == 1
    assert len(connector._sender_contexts["+2222"]) == 1
