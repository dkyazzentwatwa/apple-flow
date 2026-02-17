"""Tests for multi-workspace routing via @alias syntax."""

from codex_relay.commanding import CommandKind, parse_command
from codex_relay.models import InboundMessage
from codex_relay.orchestrator import RelayOrchestrator

from conftest import FakeConnector, FakeEgress, FakeStore


def _make_orchestrator(workspace_aliases=None):
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        allowed_workspaces=["/workspace/default", "/workspace/web-app", "/workspace/api"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
        workspace_aliases=workspace_aliases or {},
    )


# --- Command Parser Tests ---


def test_parse_command_with_workspace_alias():
    parsed = parse_command("idea: @web-app fix the CSS")
    assert parsed.kind is CommandKind.IDEA
    assert parsed.workspace == "web-app"
    assert parsed.payload == "fix the CSS"


def test_parse_command_no_alias():
    parsed = parse_command("idea: fix the CSS")
    assert parsed.kind is CommandKind.IDEA
    assert parsed.workspace == ""
    assert parsed.payload == "fix the CSS"


def test_parse_chat_with_alias():
    parsed = parse_command("@api list endpoints")
    assert parsed.kind is CommandKind.CHAT
    assert parsed.workspace == "api"
    assert parsed.payload == "list endpoints"


def test_parse_task_with_alias():
    parsed = parse_command("task: @web-app deploy to production")
    assert parsed.kind is CommandKind.TASK
    assert parsed.workspace == "web-app"
    assert parsed.payload == "deploy to production"


def test_parse_alias_with_dots_and_dashes():
    parsed = parse_command("plan: @my-app.v2 upgrade dependencies")
    assert parsed.workspace == "my-app.v2"


# --- Orchestrator Workspace Resolution Tests ---


def test_resolve_known_alias():
    orch = _make_orchestrator({"web-app": "/workspace/web-app"})
    resolved = orch._resolve_workspace("web-app")
    assert "/workspace/web-app" in resolved


def test_resolve_unknown_alias_falls_back_to_default():
    orch = _make_orchestrator({"web-app": "/workspace/web-app"})
    resolved = orch._resolve_workspace("unknown-alias")
    assert "/workspace/default" in resolved


def test_resolve_empty_alias_returns_default():
    orch = _make_orchestrator({"web-app": "/workspace/web-app"})
    resolved = orch._resolve_workspace("")
    assert "/workspace/default" in resolved


def test_workspace_alias_used_in_prompt():
    orch = _make_orchestrator({"web-app": "/workspace/web-app"})
    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="idea: @web-app fix the CSS",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.IDEA
    # The connector should have received a prompt
    assert orch.connector.turns


def test_task_with_alias_creates_run_with_workspace():
    orch = _make_orchestrator({"web-app": "/workspace/web-app"})
    msg = InboundMessage(
        id="m1",
        sender="+15551234567",
        text="task: @web-app deploy to staging",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)
    assert result.kind is CommandKind.TASK
    assert result.approval_request_id is not None
    # The run should have the web-app workspace
    run = orch.store.runs[result.run_id]
    assert "/workspace/web-app" in run["cwd"]
