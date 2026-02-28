"""Tests for orchestrator memory v2 injection behavior."""

from __future__ import annotations

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


class _LegacyMemory:
    def __init__(self, context: str):
        self._context = context

    def get_context_for_prompt(self, query: str = "") -> str:
        return self._context


class _MemoryService:
    def __init__(self, *, shadow_mode: bool, canonical: str, prompt_context: str):
        self.shadow_mode = shadow_mode
        self._canonical = canonical
        self._prompt_context = prompt_context
        self.logged: list[tuple[str, str]] = []

    def get_canonical_context(self) -> str:
        return self._canonical

    def get_context_for_prompt(self) -> str:
        return self._prompt_context

    def log_shadow_diff(self, *, legacy_context: str, canonical_context: str) -> None:
        self.logged.append((legacy_context, canonical_context))


def _msg(text: str, msg_id: str = "m1") -> InboundMessage:
    return InboundMessage(
        id=msg_id,
        sender="+15551234567",
        text=text,
        received_at="2026-02-28T12:00:00Z",
        is_from_me=False,
    )


def _orch(memory=None, memory_service=None):
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
        memory=memory,
        memory_service=memory_service,
    )


def test_memory_v2_active_injects_canonical_context():
    service = _MemoryService(
        shadow_mode=False,
        canonical="### canonical\n- keeps latest facts",
        prompt_context="### canonical\n- keeps latest facts",
    )
    orch = _orch(memory=None, memory_service=service)

    orch.handle_message(_msg("idea: design something", msg_id="m2"))

    _, prompt = orch.connector.turns[0]
    assert "Persistent memory context:" in prompt
    assert "keeps latest facts" in prompt


def test_memory_v2_shadow_mode_keeps_legacy_injection():
    legacy = _LegacyMemory("### legacy\n- trusted memory")
    service = _MemoryService(
        shadow_mode=True,
        canonical="### canonical\n- experimental memory",
        prompt_context="### canonical\n- experimental memory",
    )
    orch = _orch(memory=legacy, memory_service=service)

    orch.handle_message(_msg("plan: next steps", msg_id="m3"))

    _, prompt = orch.connector.turns[0]
    assert "Persistent memory context:" in prompt
    assert "trusted memory" in prompt
    assert "experimental memory" not in prompt
    assert service.logged == [("### legacy\n- trusted memory", "### canonical\n- experimental memory")]
