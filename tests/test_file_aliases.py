"""Tests for @f:<alias> file reference behavior."""

from pathlib import Path

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.commanding import CommandKind
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


def _make_orchestrator(tmp_path: Path, file_aliases: dict[str, str]):
    workspace = str(tmp_path.resolve())
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        allowed_workspaces=[workspace],
        default_workspace=workspace,
        require_chat_prefix=False,
        file_aliases=file_aliases,
    )


def test_file_alias_resolves_into_prompt(tmp_path: Path):
    memory_file = tmp_path / "MEMORY.md"
    memory_file.write_text("memory", encoding="utf-8")
    orch = _make_orchestrator(tmp_path, {"context-bank": str(memory_file)})

    msg = InboundMessage(
        id="m-file-alias-ok",
        sender="+15551234567",
        text="idea: summarize @f:context-bank",
        received_at="2026-02-20T10:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)

    assert result.kind is CommandKind.IDEA
    _, prompt = orch.connector.turns[0]
    assert "Referenced file aliases:" in prompt
    assert f"@f:context-bank -> {memory_file.resolve()}" in prompt
    assert str(memory_file.resolve()) in prompt


def test_file_alias_unknown_warns_and_continues(tmp_path: Path):
    orch = _make_orchestrator(tmp_path, {})

    msg = InboundMessage(
        id="m-file-alias-missing",
        sender="+15551234567",
        text="plan: use @f:context-bank for this",
        received_at="2026-02-20T10:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)

    assert result.kind is CommandKind.PLAN
    assert orch.egress.messages
    assert "File alias warnings:" in orch.egress.messages[0][1]
    assert "@f:context-bank is not configured." in orch.egress.messages[0][1]
    _, prompt = orch.connector.turns[0]
    assert "@f:context-bank" in prompt
    assert "File alias warnings:" in prompt


def test_file_alias_outside_allowed_workspace_warns(tmp_path: Path):
    outside = Path("/tmp/outside-context-bank.md")
    outside.write_text("outside", encoding="utf-8")
    orch = _make_orchestrator(tmp_path, {"context-bank": str(outside)})

    msg = InboundMessage(
        id="m-file-alias-outside",
        sender="+15551234567",
        text="idea: use @f:context-bank",
        received_at="2026-02-20T10:00:00Z",
        is_from_me=False,
    )
    orch.handle_message(msg)

    assert orch.egress.messages
    warning = orch.egress.messages[0][1]
    assert "File alias warnings:" in warning
    assert "outside allowed_workspaces" in warning


def test_file_alias_resolves_for_task_planner(tmp_path: Path):
    memory_file = tmp_path / "MEMORY.md"
    memory_file.write_text("memory", encoding="utf-8")
    orch = _make_orchestrator(tmp_path, {"context-bank": str(memory_file)})

    msg = InboundMessage(
        id="m-file-alias-task",
        sender="+15551234567",
        text="task: review @f:context-bank and propose edits",
        received_at="2026-02-20T10:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)

    assert result.kind is CommandKind.TASK
    assert result.approval_request_id is not None
    _, planner_prompt = orch.connector.turns[0]
    assert "planner mode" in planner_prompt
    assert str(memory_file.resolve()) in planner_prompt
