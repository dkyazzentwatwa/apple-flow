"""Supplementary tests for RelayOrchestrator methods not covered elsewhere."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from conftest import FakeConnector, FakeEgress, FakeStore
from apple_flow.commanding import CommandKind
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


def _make_orchestrator(
    store=None,
    egress=None,
    connector=None,
    *,
    workspace_aliases=None,
    require_chat_prefix=False,
    auto_context_messages=0,
    log_file_path=None,
):
    return RelayOrchestrator(
        connector=connector or FakeConnector(),
        egress=egress or FakeEgress(),
        store=store or FakeStore(),
        allowed_workspaces=["/workspace/default", "/workspace/alt"],
        default_workspace="/workspace/default",
        require_chat_prefix=require_chat_prefix,
        workspace_aliases=workspace_aliases or {},
        auto_context_messages=auto_context_messages,
        log_file_path=log_file_path,
    )


def _msg(text: str, sender: str = "+15551234567") -> InboundMessage:
    return InboundMessage(
        id=f"msg_{hash(text) % 99999}",
        sender=sender,
        text=text,
        received_at="2026-01-01T12:00:00Z",
        is_from_me=False,
    )


# ---------------------------------------------------------------------------
# set_run_executor
# ---------------------------------------------------------------------------

def test_set_run_executor_wires_to_approval_handler():
    orch = _make_orchestrator()
    executor = MagicMock()
    orch.set_run_executor(executor)
    assert orch._approval.run_executor is executor


# ---------------------------------------------------------------------------
# _resolve_workspace
# ---------------------------------------------------------------------------

def test_resolve_workspace_no_alias_returns_default():
    orch = _make_orchestrator()
    result = orch._resolve_workspace("")
    assert result == orch.default_workspace


def test_resolve_workspace_known_alias():
    orch = _make_orchestrator(workspace_aliases={"alt": "/workspace/alt"})
    result = orch._resolve_workspace("alt")
    assert "/workspace/alt" in result


def test_resolve_workspace_unknown_alias_returns_default():
    orch = _make_orchestrator()
    result = orch._resolve_workspace("nonexistent")
    assert result == orch.default_workspace


def test_resolve_workspace_alias_to_disallowed_returns_default():
    orch = _make_orchestrator(workspace_aliases={"bad": "/not/allowed"})
    result = orch._resolve_workspace("bad")
    assert result == orch.default_workspace


# ---------------------------------------------------------------------------
# deny_all command
# ---------------------------------------------------------------------------

def test_deny_all_cancels_pending_approvals():
    store = FakeStore()
    store.create_run("run_1", "+1", "task", "awaiting_approval", "/tmp", "execute")
    store.create_run("run_2", "+1", "task", "awaiting_approval", "/tmp", "execute")
    store.create_approval("req_1", "run_1", "s", "p", "2030-01-01T00:00:00Z", "+1")
    store.create_approval("req_2", "run_2", "s", "p", "2030-01-01T00:00:00Z", "+1")
    egress = FakeEgress()
    orch = _make_orchestrator(store=store, egress=egress)

    result = orch.handle_message(_msg("deny all"))

    assert result.kind == CommandKind.DENY_ALL
    assert len(store.list_pending_approvals()) == 0
    assert "Cancelled" in result.response


def test_deny_all_with_no_pending():
    egress = FakeEgress()
    orch = _make_orchestrator(egress=egress)

    result = orch.handle_message(_msg("deny all"))

    assert "No pending" in result.response


# ---------------------------------------------------------------------------
# _handle_history
# ---------------------------------------------------------------------------

def test_handle_history_no_messages():
    class EmptyHistoryStore(FakeStore):
        def recent_messages(self, sender, limit=10):
            return []

    store = EmptyHistoryStore()
    orch = _make_orchestrator(store=store)

    result = orch.handle_message(_msg("history:"))

    assert result.kind == CommandKind.HISTORY
    assert "No message history found" in result.response


def test_handle_history_with_recent_messages():
    store = FakeStore()
    store.messages["m1"] = {
        "text": "hello world",
        "received_at": "2026-01-01T10:00:00Z",
        "sender": "+15551234567",
    }
    # Implement recent_messages on FakeStore
    store.recent_messages = lambda sender, limit=10: [
        {"text": "hello world", "received_at": "2026-01-01T10:00:00Z"}
    ]
    orch = _make_orchestrator(store=store)

    result = orch.handle_message(_msg("history:"))

    assert result.kind == CommandKind.HISTORY
    assert "hello world" in result.response


def test_handle_history_with_search():
    store = FakeStore()
    store.search_messages = lambda sender, query, limit=10: [
        {"text": "hello world query", "received_at": "2026-01-01T10:00:00Z"}
    ]
    orch = _make_orchestrator(store=store)

    result = orch.handle_message(_msg("history: hello"))

    assert result.kind == CommandKind.HISTORY
    assert "hello" in result.response


def test_handle_history_search_no_results():
    store = FakeStore()
    store.search_messages = lambda sender, query, limit=10: []
    orch = _make_orchestrator(store=store)

    result = orch.handle_message(_msg("history: xyz"))

    assert "No messages found" in result.response


# ---------------------------------------------------------------------------
# _provider_label
# ---------------------------------------------------------------------------

def test_provider_label_claude():
    from apple_flow.claude_cli_connector import ClaudeCliConnector
    orch = _make_orchestrator(connector=ClaudeCliConnector())
    assert orch._provider_label() == "Claude"


def test_provider_label_codex():
    from apple_flow.codex_cli_connector import CodexCliConnector
    orch = _make_orchestrator(connector=CodexCliConnector())
    assert orch._provider_label() == "Codex"


def test_provider_label_unknown():
    orch = _make_orchestrator(connector=FakeConnector())
    # FakeConnector has no known name
    label = orch._provider_label()
    assert isinstance(label, str)


# ---------------------------------------------------------------------------
# _provider_command_patterns
# ---------------------------------------------------------------------------

def test_provider_command_patterns_returns_list():
    orch = _make_orchestrator()
    patterns = orch._provider_command_patterns()
    assert isinstance(patterns, list)


def test_provider_command_patterns_no_duplicates():
    orch = _make_orchestrator()
    patterns = orch._provider_command_patterns()
    assert len(patterns) == len(set(patterns))


# ---------------------------------------------------------------------------
# _collect_descendants (static)
# ---------------------------------------------------------------------------

def test_collect_descendants_direct_children():
    # pid 100 has children 101, 102
    table = {
        100: (1, "root"),
        101: (100, "child1"),
        102: (100, "child2"),
        200: (1, "unrelated"),
    }
    descendants = RelayOrchestrator._collect_descendants(table, 100)
    assert descendants == {101, 102}


def test_collect_descendants_nested():
    table = {
        100: (1, "root"),
        101: (100, "child"),
        102: (101, "grandchild"),
    }
    descendants = RelayOrchestrator._collect_descendants(table, 100)
    assert descendants == {101, 102}


def test_collect_descendants_no_children():
    table = {100: (1, "leaf")}
    descendants = RelayOrchestrator._collect_descendants(table, 100)
    assert descendants == set()


def test_collect_descendants_empty_table():
    descendants = RelayOrchestrator._collect_descendants({}, 100)
    assert descendants == set()


# ---------------------------------------------------------------------------
# _pid_alive (static)
# ---------------------------------------------------------------------------

def test_pid_alive_current_process():
    # Current process must be alive
    assert RelayOrchestrator._pid_alive(os.getpid()) is True


def test_pid_alive_nonexistent_pid():
    # PID 0 or a very large PID that won't exist
    # Use a definitely-dead PID by checking one that doesn't exist
    result = RelayOrchestrator._pid_alive(99999999)
    assert result is False


# ---------------------------------------------------------------------------
# _load_process_table (static)
# ---------------------------------------------------------------------------

def test_load_process_table_returns_dict():
    table = RelayOrchestrator._load_process_table()
    assert isinstance(table, dict)


def test_load_process_table_on_error_returns_empty():
    with patch("subprocess.run", side_effect=OSError("ps not found")):
        table = RelayOrchestrator._load_process_table()
    assert table == {}


def test_load_process_table_nonzero_returncode_returns_empty():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    with patch("subprocess.run", return_value=mock_result):
        table = RelayOrchestrator._load_process_table()
    assert table == {}


# ---------------------------------------------------------------------------
# _parse_timestamp_utc (static)
# ---------------------------------------------------------------------------

def test_parse_timestamp_utc_valid():
    dt = RelayOrchestrator._parse_timestamp_utc("2026-01-01T12:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_timestamp_utc_none():
    assert RelayOrchestrator._parse_timestamp_utc(None) is None


def test_parse_timestamp_utc_empty():
    assert RelayOrchestrator._parse_timestamp_utc("") is None


def test_parse_timestamp_utc_invalid():
    assert RelayOrchestrator._parse_timestamp_utc("not-a-date") is None


# ---------------------------------------------------------------------------
# _mark_restart_echo_suppress
# ---------------------------------------------------------------------------

def test_mark_restart_echo_suppress_writes_state():
    store = FakeStore()
    orch = _make_orchestrator(store=store)
    orch._mark_restart_echo_suppress("+15551234567", "Apple Flow restarting...")
    raw = store.get_state("system_restart_echo_suppress")
    assert raw is not None
    data = json.loads(raw)
    assert data["sender"] == "+15551234567"
    assert "expires_at" in data


def test_mark_restart_echo_suppress_exception_safe():
    store = FakeStore()
    store.set_state = MagicMock(side_effect=RuntimeError("state error"))
    orch = _make_orchestrator(store=store)
    # Should not raise
    orch._mark_restart_echo_suppress("+15551234567", "text")


# ---------------------------------------------------------------------------
# _inject_auto_context
# ---------------------------------------------------------------------------

def test_inject_auto_context_disabled():
    orch = _make_orchestrator(auto_context_messages=0)
    result = orch._inject_auto_context("+1", "original prompt")
    assert result == "original prompt"


def test_inject_auto_context_enabled_no_messages():
    store = FakeStore()
    store.recent_messages = lambda sender, limit=10: []
    orch = _make_orchestrator(store=store, auto_context_messages=3)
    result = orch._inject_auto_context("+1", "my prompt")
    assert result == "my prompt"


def test_inject_auto_context_enabled_with_messages():
    store = FakeStore()
    store.recent_messages = lambda sender, limit=10: [
        {"text": "prev message", "received_at": "2026-01-01T10:00:00Z"},
    ]
    orch = _make_orchestrator(store=store, auto_context_messages=3)
    result = orch._inject_auto_context("+1", "new prompt")
    assert "Recent conversation history:" in result
    assert "prev message" in result
    assert "new prompt" in result


def test_inject_auto_context_store_without_recent_messages():
    orch = _make_orchestrator(auto_context_messages=3)
    # FakeStore has no recent_messages attribute
    result = orch._inject_auto_context("+1", "prompt")
    assert result == "prompt"


# ---------------------------------------------------------------------------
# _inject_memory_context
# ---------------------------------------------------------------------------

def test_inject_memory_context_no_memory():
    orch = _make_orchestrator()
    result = orch._inject_memory_context("prompt")
    assert result == "prompt"


def test_inject_memory_context_with_memory_service():
    memory_service = MagicMock()
    memory_service.get_context_for_prompt.return_value = "memory content"
    orch = _make_orchestrator()
    orch.memory_service = memory_service
    result = orch._inject_memory_context("prompt")
    assert "Persistent memory context:" in result
    assert "memory content" in result
    assert "prompt" in result


def test_inject_memory_context_with_legacy_memory():
    memory = MagicMock()
    memory.get_context_for_prompt.return_value = "legacy memory"
    orch = _make_orchestrator()
    orch.memory = memory
    result = orch._inject_memory_context("prompt")
    assert "Persistent memory context:" in result
    assert "legacy memory" in result


def test_inject_memory_context_memory_exception_is_safe():
    memory_service = MagicMock()
    memory_service.get_context_for_prompt.side_effect = RuntimeError("memory error")
    orch = _make_orchestrator()
    orch.memory_service = memory_service
    # Should return original prompt without raising
    result = orch._inject_memory_context("prompt")
    assert result == "prompt"


def test_inject_memory_context_empty_context():
    memory_service = MagicMock()
    memory_service.get_context_for_prompt.return_value = ""
    orch = _make_orchestrator()
    orch.memory_service = memory_service
    result = orch._inject_memory_context("prompt")
    assert result == "prompt"


# ---------------------------------------------------------------------------
# _build_non_mutating_prompt
# ---------------------------------------------------------------------------

def test_build_non_mutating_idea():
    orch = _make_orchestrator()
    prompt = orch._build_non_mutating_prompt(CommandKind.IDEA, "implement caching", "/workspace")
    assert "brainstorm mode" in prompt
    assert "implement caching" in prompt


def test_build_non_mutating_plan():
    orch = _make_orchestrator()
    prompt = orch._build_non_mutating_prompt(CommandKind.PLAN, "add login", "/workspace")
    assert "planning mode" in prompt
    assert "add login" in prompt


def test_build_non_mutating_chat():
    orch = _make_orchestrator()
    prompt = orch._build_non_mutating_prompt(CommandKind.CHAT, "hello there", "/workspace")
    assert "hello there" in prompt


# ---------------------------------------------------------------------------
# _run_connector_turn
# ---------------------------------------------------------------------------

def test_run_connector_turn_without_options():
    connector = FakeConnector()
    orch = _make_orchestrator(connector=connector)
    result = orch._run_connector_turn("thread_1", "prompt text")
    assert result == "assistant-response"
    assert len(connector.turns) == 1


def test_run_connector_turn_with_team_context_codex_config():
    connector = MagicMock()
    connector.run_turn = MagicMock(return_value="response")
    orch = _make_orchestrator(connector=connector)
    team_context = {"codex_config_path": "/path/to/config.json"}
    orch._run_connector_turn("thread_1", "prompt", team_context=team_context, allow_tools=True)
    # Should have passed options with codex_config_path
    call_kwargs = connector.run_turn.call_args
    assert call_kwargs is not None


def test_run_connector_turn_fallback_on_type_error():
    """Connector without options param should fall back to positional call."""
    connector = FakeConnector()  # run_turn doesn't accept options kwarg
    orch = _make_orchestrator(connector=connector)
    team_context = {"codex_config_path": "/path/to/config.json"}
    # Should not raise even though FakeConnector.run_turn doesn't accept options
    result = orch._run_connector_turn("t1", "prompt", team_context=team_context)
    assert result is not None


# ---------------------------------------------------------------------------
# _inject_attachment_context
# ---------------------------------------------------------------------------

def test_inject_attachment_context_disabled():
    orch = _make_orchestrator()
    msg = _msg("hello")
    result = orch._inject_attachment_context(msg, "base prompt")
    assert result == "base prompt"


def test_inject_attachment_context_with_prompt_block():
    orch = _make_orchestrator()
    orch.enable_attachments = True
    msg = _msg("hello")
    msg.context["attachment_prompt_block"] = "Attachment analysis: image.png is a diagram"
    result = orch._inject_attachment_context(msg, "base prompt")
    assert "Attachment analysis" in result
    assert "base prompt" in result


def test_inject_attachment_context_with_raw_attachments():
    orch = _make_orchestrator()
    orch.enable_attachments = True
    msg = _msg("hello")
    msg.context["attachments"] = [
        {"filename": "doc.pdf", "mime_type": "application/pdf", "path": "/tmp/doc.pdf"}
    ]
    result = orch._inject_attachment_context(msg, "base prompt")
    assert "doc.pdf" in result
    assert "Attached files:" in result


def test_inject_attachment_context_no_attachments():
    orch = _make_orchestrator()
    orch.enable_attachments = True
    msg = _msg("hello")
    result = orch._inject_attachment_context(msg, "base prompt")
    assert result == "base prompt"


# ---------------------------------------------------------------------------
# system: mute/unmute
# ---------------------------------------------------------------------------

def test_system_mute_sets_state():
    store = FakeStore()
    orch = _make_orchestrator(store=store)

    result = orch.handle_message(_msg("system: mute"))

    assert result.kind == CommandKind.SYSTEM
    assert store.get_state("companion_muted") == "true"
    assert "muted" in result.response.lower()


def test_system_unmute_sets_state():
    store = FakeStore()
    store.set_state("companion_muted", "true")
    orch = _make_orchestrator(store=store)

    result = orch.handle_message(_msg("system: unmute"))

    assert store.get_state("companion_muted") == "false"
    assert "unmuted" in result.response.lower() or "re-enabled" in result.response.lower()


# ---------------------------------------------------------------------------
# duplicate message suppression
# ---------------------------------------------------------------------------

def test_duplicate_message_returns_early():
    store = FakeStore()
    egress = FakeEgress()
    orch = _make_orchestrator(store=store, egress=egress)
    msg = _msg("hello world")

    # First call inserts
    orch.handle_message(msg)
    msg_count_before = len(egress.messages)

    # Second call with same ID should be suppressed
    result = orch.handle_message(msg)
    assert result.response == "duplicate"
    assert len(egress.messages) == msg_count_before  # no new messages


# ---------------------------------------------------------------------------
# Empty message handling
# ---------------------------------------------------------------------------

def test_empty_message_returns_ignored():
    orch = _make_orchestrator()
    msg = InboundMessage(
        id="empty_msg",
        sender="+15551234567",
        text="   ",
        received_at="2026-01-01T12:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert result.response == "ignored_empty"
