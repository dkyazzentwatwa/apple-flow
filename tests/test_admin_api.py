from fastapi.testclient import TestClient

from apple_flow.main import build_app


class InMemoryStore:
    def __init__(self):
        self._sessions = [{"sender": "+1", "thread_id": "t1", "mode": "chat", "last_seen_at": "now"}]
        self._approvals = [{"request_id": "req1", "status": "pending"}]
        self._runs = {"run1": {"run_id": "run1", "state": "running"}}
        self._state = {
            "gateway_health_notes": '{"healthy": false, "last_failure_reason": "Connection invalid"}',
            "daemon_loop_health_imessage": (
                '{"healthy": true, "last_success_at": "2026-03-11T12:00:00+00:00", "restart_count": 1}'
            ),
            "daemon_watchdog": (
                '{"healthy": false, "degraded_reasons": ["poll_stalled"], '
                '"last_connector_completion_at": "2026-03-11T12:01:00+00:00", '
                '"oldest_inflight_dispatch_seconds": 12.0, "active_helper_count": 2, '
                '"oldest_helper_age_seconds": 140.0, "event_loop_lag_seconds": 0.25}'
            ),
        }

    def list_sessions(self):
        return self._sessions

    def list_pending_approvals(self):
        return self._approvals

    def get_run(self, run_id):
        return self._runs.get(run_id)

    def resolve_approval(self, request_id, status):
        return True

    def get_state(self, key):
        return self._state.get(key)



def test_admin_endpoints_expose_state():
    import os

    old_token = os.environ.get("apple_flow_admin_api_token")
    os.environ["apple_flow_admin_api_token"] = ""
    try:
        app = build_app(store=InMemoryStore())
        client = TestClient(app)

        assert client.get("/health").status_code == 200
        assert client.get("/sessions").status_code == 200
        assert client.get("/approvals/pending").status_code == 200
        assert client.get("/runs/run1").status_code == 200
        assert client.post("/approvals/req1/override", json={"status": "approved"}).status_code == 200
    finally:
        if old_token is not None:
            os.environ["apple_flow_admin_api_token"] = old_token
        else:
            os.environ.pop("apple_flow_admin_api_token", None)


def test_admin_health_includes_gateway_status():
    import os

    old_token = os.environ.get("apple_flow_admin_api_token")
    os.environ["apple_flow_admin_api_token"] = ""
    try:
        app = build_app(store=InMemoryStore())
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "degraded"
        assert payload["gateways"]["notes"]["healthy"] is False
        assert payload["gateways"]["notes"]["last_failure_reason"] == "Connection invalid"
        assert payload["runtime"]["watchdog"]["healthy"] is False
        assert payload["runtime"]["loops"]["imessage"]["restart_count"] == 1
        assert payload["runtime"]["watchdog"]["active_helper_count"] == 2
    finally:
        if old_token is not None:
            os.environ["apple_flow_admin_api_token"] = old_token
        else:
            os.environ.pop("apple_flow_admin_api_token", None)
