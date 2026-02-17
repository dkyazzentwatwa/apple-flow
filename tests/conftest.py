"""Shared test fixtures for Codex Relay tests."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@dataclass
class FakeConnector:
    """Fake connector for testing orchestrator logic."""

    created: list[str] = field(default_factory=list)
    turns: list[tuple[str, str]] = field(default_factory=list)

    def get_or_create_thread(self, sender: str) -> str:
        self.created.append(sender)
        return "thread_abc"

    def reset_thread(self, sender: str) -> str:
        self.created.append(f"reset:{sender}")
        return "thread_reset"

    def run_turn(self, thread_id: str, prompt: str) -> str:
        self.turns.append((thread_id, prompt))
        if "planner" in prompt:
            return "PLAN: Create files and tests"
        if "verifier" in prompt:
            return "VERIFIED: checks complete"
        return "assistant-response"

    def ensure_started(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


class FakeEgress:
    """Fake egress for testing message sending."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, recipient: str, text: str) -> None:
        self.messages.append((recipient, text))

    def was_recent_outbound(self, sender: str, text: str) -> bool:
        return False

    def mark_outbound(self, recipient: str, text: str) -> None:
        pass


class FakeStore:
    """Fake store for testing orchestrator logic."""

    def __init__(self) -> None:
        self.approvals: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.state: dict[str, str] = {}

    def bootstrap(self) -> None:
        pass

    def close(self) -> None:
        pass

    def record_message(
        self, message_id: str, sender: str, text: str, received_at: str, dedupe_hash: str
    ) -> bool:
        if message_id in self.messages:
            return False
        self.messages[message_id] = {
            "sender": sender,
            "text": text,
            "received_at": received_at,
            "dedupe_hash": dedupe_hash,
        }
        return True

    def get_session(self, sender: str) -> dict[str, Any] | None:
        return self.sessions.get(sender)

    def upsert_session(self, sender: str, thread_id: str, mode: str) -> None:
        self.sessions[sender] = {"thread_id": thread_id, "mode": mode}

    def list_sessions(self) -> list[dict[str, Any]]:
        return list(self.sessions.values())

    def create_run(
        self, run_id: str, sender: str, intent: str, state: str, cwd: str, risk_level: str
    ) -> None:
        self.runs[run_id] = {
            "run_id": run_id,
            "state": state,
            "sender": sender,
            "intent": intent,
            "cwd": cwd,
            "risk_level": risk_level,
        }

    def update_run_state(self, run_id: str, state: str) -> None:
        if run_id in self.runs:
            self.runs[run_id]["state"] = state

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.runs.get(run_id)

    def create_approval(
        self,
        request_id: str,
        run_id: str,
        summary: str,
        command_preview: str,
        expires_at: str,
        sender: str,
    ) -> None:
        self.approvals[request_id] = {
            "request_id": request_id,
            "run_id": run_id,
            "sender": sender,
            "summary": summary,
            "command_preview": command_preview,
            "expires_at": expires_at,
            "status": "pending",
        }

    def get_approval(self, request_id: str) -> dict[str, Any] | None:
        return self.approvals.get(request_id)

    def resolve_approval(self, request_id: str, status: str) -> bool:
        if request_id in self.approvals:
            self.approvals[request_id]["status"] = status
            return True
        return False

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return [a for a in self.approvals.values() if a.get("status") == "pending"]

    def create_event(
        self, event_id: str, run_id: str, step: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        self.events.append(
            {
                "event_id": event_id,
                "run_id": run_id,
                "step": step,
                "event_type": event_type,
                "payload": payload,
            }
        )

    def list_events(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.events[:limit]

    def set_state(self, key: str, value: str) -> None:
        self.state[key] = value

    def get_state(self, key: str) -> str | None:
        return self.state.get(key)

    def get_stats(self) -> dict[str, Any]:
        runs_by_state: dict[str, int] = {}
        for run in self.runs.values():
            state = run.get("state", "unknown")
            runs_by_state[state] = runs_by_state.get(state, 0) + 1
        return {
            "active_sessions": len(self.sessions),
            "total_messages": len(self.messages),
            "pending_approvals": len(self.list_pending_approvals()),
            "runs_by_state": runs_by_state,
            "last_event": self.events[-1] if self.events else None,
        }

    def recent_messages(self, sender: str, limit: int = 10) -> list[dict[str, Any]]:
        sender_msgs = [
            m for mid, m in self.messages.items() if m.get("sender") == sender
        ]
        return sender_msgs[:limit]

    def search_messages(self, sender: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
        results = [
            m for mid, m in self.messages.items()
            if m.get("sender") == sender and query.lower() in (m.get("text", "")).lower()
        ]
        return results[:limit]


@pytest.fixture
def fake_connector() -> FakeConnector:
    """Provide a fake connector for tests."""
    return FakeConnector()


@pytest.fixture
def fake_egress() -> FakeEgress:
    """Provide a fake egress for tests."""
    return FakeEgress()


@pytest.fixture
def fake_store() -> FakeStore:
    """Provide a fake store for tests."""
    return FakeStore()
