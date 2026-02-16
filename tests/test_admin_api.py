from fastapi.testclient import TestClient

from codex_relay.main import build_app


class InMemoryStore:
    def __init__(self):
        self._sessions = [{"sender": "+1", "thread_id": "t1", "mode": "chat", "last_seen_at": "now"}]
        self._approvals = [{"request_id": "req1", "status": "pending"}]
        self._runs = {"run1": {"run_id": "run1", "state": "running"}}

    def list_sessions(self):
        return self._sessions

    def list_pending_approvals(self):
        return self._approvals

    def get_run(self, run_id):
        return self._runs.get(run_id)

    def resolve_approval(self, request_id, status):
        return True



def test_admin_endpoints_expose_state():
    app = build_app(store=InMemoryStore())
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/sessions").status_code == 200
    assert client.get("/approvals/pending").status_code == 200
    assert client.get("/runs/run1").status_code == 200
    assert client.post("/approvals/req1/override", json={"status": "approved"}).status_code == 200
