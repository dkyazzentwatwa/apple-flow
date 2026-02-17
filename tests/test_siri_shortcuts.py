"""Tests for the Siri Shortcuts Bridge (POST /task endpoint)."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from apple_flow.commanding import CommandKind
from apple_flow.main import build_app
from apple_flow.orchestrator import OrchestrationResult


class TaskStore:
    """Minimal store for task submission tests."""

    def __init__(self):
        self._sessions = []
        self._approvals = []
        self._runs = {}
        self._messages = {}

    def list_sessions(self):
        return self._sessions

    def list_pending_approvals(self):
        return self._approvals

    def get_run(self, run_id):
        return self._runs.get(run_id)

    def resolve_approval(self, request_id, status):
        return True

    def list_events(self, limit=200):
        return []


def test_task_endpoint_returns_503_without_orchestrator():
    app = build_app(store=TaskStore())
    client = TestClient(app)

    resp = client.post("/task", json={"sender": "+15551234567", "text": "idea: test"})
    assert resp.status_code == 503
    assert "Orchestrator not available" in resp.json()["detail"]


def test_task_endpoint_processes_message():
    import os
    # Temporarily clear allowed_senders so no sender check blocks us
    old_val = os.environ.get("apple_flow_allowed_senders")
    os.environ["apple_flow_allowed_senders"] = ""
    try:
        app = build_app(store=TaskStore())
        mock_orch = MagicMock()
        mock_orch.handle_message.return_value = OrchestrationResult(
            kind=CommandKind.IDEA,
            response="Here are some ideas...",
            run_id=None,
            approval_request_id=None,
        )
        app.state.orchestrator = mock_orch
        client = TestClient(app)

        resp = client.post("/task", json={"sender": "+15551234567", "text": "idea: test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "idea"
        assert data["response"] == "Here are some ideas..."
        assert mock_orch.handle_message.called
    finally:
        if old_val is not None:
            os.environ["apple_flow_allowed_senders"] = old_val
        else:
            os.environ.pop("apple_flow_allowed_senders", None)


def test_task_endpoint_validates_sender():
    """When allowed_senders is set, non-allowlisted senders get 403."""
    import os
    old_val = os.environ.get("apple_flow_allowed_senders")
    os.environ["apple_flow_allowed_senders"] = "+15551234567"
    try:
        app = build_app(store=TaskStore())
        mock_orch = MagicMock()
        app.state.orchestrator = mock_orch
        client = TestClient(app)

        resp = client.post("/task", json={"sender": "+19999999999", "text": "idea: test"})
        assert resp.status_code == 403
    finally:
        if old_val is not None:
            os.environ["apple_flow_allowed_senders"] = old_val
        else:
            os.environ.pop("apple_flow_allowed_senders", None)


def test_task_endpoint_requires_fields():
    app = build_app(store=TaskStore())
    app.state.orchestrator = MagicMock()
    client = TestClient(app)

    # Missing text
    resp = client.post("/task", json={"sender": "+15551234567"})
    assert resp.status_code == 422

    # Missing sender
    resp = client.post("/task", json={"text": "hello"})
    assert resp.status_code == 422

    # Empty sender
    resp = client.post("/task", json={"sender": "", "text": "hello"})
    assert resp.status_code == 422
