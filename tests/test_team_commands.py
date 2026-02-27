from __future__ import annotations

from datetime import UTC, datetime

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


def _make_orchestrator(
    connector: FakeConnector,
    egress: FakeEgress,
    store: FakeStore,
    *,
    require_chat_prefix: bool = True,
) -> RelayOrchestrator:
    return RelayOrchestrator(
        connector=connector,
        egress=egress,
        store=store,
        allowed_workspaces=["/Users/cypher/Public/code/codex-flow"],
        default_workspace="/Users/cypher/Public/code/codex-flow",
        require_chat_prefix=require_chat_prefix,
        chat_prefix="relay:",
    )


def _msg(mid: str, text: str, sender: str = "+15551234567") -> InboundMessage:
    return InboundMessage(
        id=mid,
        sender=sender,
        text=text,
        received_at=datetime.now(UTC).isoformat(),
        is_from_me=False,
    )


def test_teams_list_works_without_chat_prefix():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    orchestrator = _make_orchestrator(connector, egress, store, require_chat_prefix=True)

    orchestrator.handle_message(_msg("team_list_1", "list available agent teams"))

    assert egress.messages
    assert "Available agent teams:" in egress.messages[-1][1]
    assert "codebase-exploration-team" in egress.messages[-1][1]


def test_load_current_and_unload_team():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    orchestrator = _make_orchestrator(connector, egress, store, require_chat_prefix=True)

    orchestrator.handle_message(_msg("team_load_1", "system: team load codebase-exploration-team"))
    orchestrator.handle_message(_msg("team_current_1", "what team is active"))
    assert "codebase-exploration-team" in egress.messages[-1][1]

    orchestrator.handle_message(_msg("team_unload_1", "unload team"))
    orchestrator.handle_message(_msg("team_current_2", "system: team current"))
    assert "No active team loaded" in egress.messages[-1][1]


def test_load_with_follow_on_runs_once_and_auto_expires():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    orchestrator = _make_orchestrator(connector, egress, store, require_chat_prefix=True)

    orchestrator.handle_message(
        _msg(
            "team_combo_1",
            "load up the codebase-exploration-team and research new features",
        )
    )

    assert any("Loaded team `codebase-exploration-team`" in text for _, text in egress.messages)
    assert any("assistant-response" in text for _, text in egress.messages)

    orchestrator.handle_message(_msg("team_current_3", "system: team current"))
    assert "No active team loaded" in egress.messages[-1][1]


def test_unknown_team_returns_suggestions():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    orchestrator = _make_orchestrator(connector, egress, store, require_chat_prefix=True)

    orchestrator.handle_message(_msg("team_unknown_1", "system: team load nope-nope"))

    assert "Unknown team" in egress.messages[-1][1]
    assert "Closest matches:" in egress.messages[-1][1]


def test_task_flow_persists_team_context_in_run_source_context():
    connector = FakeConnector()
    egress = FakeEgress()
    store = FakeStore()
    orchestrator = _make_orchestrator(connector, egress, store, require_chat_prefix=True)

    orchestrator.handle_message(_msg("team_task_1", "system: team load codebase-exploration-team"))
    result = orchestrator.handle_message(_msg("team_task_2", "task: implement feature flag"))

    assert result.run_id is not None
    source_context = store.get_run_source_context(result.run_id)
    assert isinstance(source_context, dict)
    assert isinstance(source_context.get("team_context"), dict)
    assert source_context["team_context"].get("slug") == "codebase-exploration-team"

    orchestrator.handle_message(_msg("team_current_4", "system: team current"))
    assert "No active team loaded" in egress.messages[-1][1]
