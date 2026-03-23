from datetime import UTC, datetime
from pathlib import Path

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

    def set_state(self, key, value):
        self._state[key] = value


def _write_agent_office_fixture(office: Path) -> None:
    (office / "00_inbox").mkdir(parents=True, exist_ok=True)
    (office / "10_daily").mkdir(parents=True, exist_ok=True)
    (office / "60_memory").mkdir(parents=True, exist_ok=True)
    (office / "30_outputs").mkdir(parents=True, exist_ok=True)
    (office / "40_resources").mkdir(parents=True, exist_ok=True)
    (office / "90_logs").mkdir(parents=True, exist_ok=True)
    logs_dir = office.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    (office / "SOUL.md").write_text("You are Flow.\n", encoding="utf-8")
    (office / "00_inbox" / "inbox.md").write_text(
        "# Inbox\n\n## Entries\n- [ ] Inbox item one\n- [x] Inbox item done\n",
        encoding="utf-8",
    )
    (office / "10_daily" / "2026-03-22.md").write_text(
        "# Daily Note\n\n## Morning Briefing\nToday looks good.\n",
        encoding="utf-8",
    )
    (office / "MEMORY.md").write_text("# Memory\n\n## Durable\nImportant note.\n", encoding="utf-8")
    (office / "60_memory" / "topic.md").write_text("# Topic\nMemory body.\n", encoding="utf-8")
    (office / "30_outputs" / "output.md").write_text("# Output\nOutput body.\n", encoding="utf-8")
    (office / "40_resources" / "resource.md").write_text("# Resource\nResource body.\n", encoding="utf-8")
    (office / "90_logs" / "automation-log.md").write_text("# Log\n", encoding="utf-8")
    (office / "90_logs" / "events.csv").write_text("id,timestamp,event\n1,now,test\n", encoding="utf-8")
    (logs_dir / "apple-flow.err.log").write_text(
        "daemon err line 1\ndaemon err line 2\nERROR AppleScript timeout while polling inbox\n",
        encoding="utf-8",
    )
    (logs_dir / "apple-flow-admin.err.log").write_text(
        "admin err line 1\nadmin err line 2\n",
        encoding="utf-8",
    )
    (logs_dir / "apple-flow-admin.log").write_text(
        "admin log line 1\nadmin log line 2\n",
        encoding="utf-8",
    )
    (logs_dir / "apple-flow.log").write_text(
        "daemon out line 1\ndaemon out line 2\n",
        encoding="utf-8",
    )



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


def test_dashboard_routes_require_auth(monkeypatch, tmp_path):
    office = tmp_path / "agent-office"
    _write_agent_office_fixture(office)
    monkeypatch.setenv("apple_flow_admin_api_token", "secret-token")
    monkeypatch.setenv("apple_flow_soul_file", str(office / "SOUL.md"))

    app = build_app(store=InMemoryStore())
    client = TestClient(app)

    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 200
    assert "Agent Office Dashboard" in dashboard_response.text
    assert 'action="/dashboard/bootstrap"' in dashboard_response.text
    assert client.get("/dashboard/api/summary").status_code == 401
    assert client.get("/dashboard/api/section/inbox").status_code == 401
    assert client.get("/dashboard/api/item?section=inbox").status_code == 401
    assert client.post("/dashboard/bootstrap", data={"dashboard_token": "wrong"}).status_code == 401


def test_dashboard_summary_and_section_expose_agent_office_state(monkeypatch, tmp_path):
    office = tmp_path / "agent-office"
    _write_agent_office_fixture(office)
    monkeypatch.setenv("apple_flow_admin_api_token", "secret-token")
    monkeypatch.setenv("apple_flow_soul_file", str(office / "SOUL.md"))

    app = build_app(store=InMemoryStore())
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret-token"}

    summary_response = client.get("/dashboard/api/summary", headers=headers)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["agent_office_path"] == str(office)
    assert summary["inbox"]["unchecked_count"] == 1
    assert summary["runtime"]["pending_approvals_count"] == 1
    assert summary["companion"]["muted"] is False
    assert summary["inbox"]["freshness"]["state"] in {"fresh", "quiet"}
    assert summary["recent"]["freshness"]["state"] in {"fresh", "quiet"}

    section_response = client.get("/dashboard/api/section/inbox", headers=headers)
    assert section_response.status_code == 200
    section = section_response.json()
    assert section["section"] == "inbox"
    assert section["data"]["unchecked_count"] == 1

    item_response = client.get("/dashboard/api/item?section=inbox", headers=headers)
    assert item_response.status_code == 200
    item = item_response.json()
    assert item["section"] == "inbox"
    assert item["content_kind"] == "markdown"
    assert "Inbox item one" in item["content"]
    assert item["freshness"]["state"] in {"fresh", "quiet"}

    log_item_response = client.get(
        "/dashboard/api/item?section=recent&bucket=logs&name=apple-flow.err.log",
        headers=headers,
    )
    assert log_item_response.status_code == 200
    log_item = log_item_response.json()
    assert log_item["section"] == "recent"
    assert log_item["bucket"] == "logs"
    assert "AppleScript timeout" in log_item["content"]


def test_dashboard_summary_uses_project_timezone_for_daily_note(monkeypatch, tmp_path):
    office = tmp_path / "agent-office"
    _write_agent_office_fixture(office)
    monkeypatch.setenv("apple_flow_admin_api_token", "secret-token")
    monkeypatch.setenv("apple_flow_soul_file", str(office / "SOUL.md"))
    monkeypatch.setenv("apple_flow_timezone", "America/Los_Angeles")
    monkeypatch.setattr(
        "apple_flow.main._dashboard_now",
        lambda _settings: datetime(2026, 3, 23, 6, 30, tzinfo=UTC),
    )

    app = build_app(store=InMemoryStore())
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret-token"}

    summary_response = client.get("/dashboard/api/summary", headers=headers)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["daily"]["today_exists"] is True
    assert summary["daily"]["today_path"].endswith("2026-03-22.md")
    assert not summary["daily"]["today_path"].endswith("2026-03-23.md")


def test_dashboard_shell_serves_html(monkeypatch, tmp_path):
    office = tmp_path / "agent-office"
    _write_agent_office_fixture(office)
    monkeypatch.setenv("apple_flow_admin_api_token", "secret-token")
    monkeypatch.setenv("apple_flow_soul_file", str(office / "SOUL.md"))

    app = build_app(store=InMemoryStore())
    client = TestClient(app)

    bootstrap = client.post("/dashboard/bootstrap", data={"dashboard_token": "secret-token"}, follow_redirects=False)
    assert bootstrap.status_code == 303
    assert "apple_flow_dashboard_token=secret-token" in bootstrap.headers["set-cookie"]
    assert "HttpOnly" in bootstrap.headers["set-cookie"]
    assert "Path=/dashboard" in bootstrap.headers["set-cookie"]

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Agent Office Dashboard" in body
    assert "America/Los_Angeles" in body
    assert 'id="runtime-status"' in body
    assert 'id="attention-count"' in body
    assert 'id="companion-action-button"' in body
    assert 'id="runtime-freshness"' in body
    assert 'data-section="inbox"' in body
    assert 'data-section="memory"' in body
    assert "/dashboard/api/summary" in body
    assert "refresh-button" in body
    assert "section-detail" in body
    assert 'id="recent-logs-panel"' in body
    assert 'id="recent-logs-toggle"' in body
    assert 'id="recent-logs-detail"' in body
    assert 'id="detail-modal"' in body
    assert 'id="detail-modal-title"' in body
    assert 'id="detail-modal-content"' in body
    assert 'id="detail-modal-close"' in body
    assert "/dashboard/api/item" in body
    assert "secret-token" not in body

    summary_response = client.get("/dashboard/api/summary")
    assert summary_response.status_code == 200
    assert summary_response.json()["agent_office_path"] == str(office)
    assert client.get("/sessions").status_code == 401


def test_dashboard_companion_actions_require_auth(monkeypatch, tmp_path):
    office = tmp_path / "agent-office"
    _write_agent_office_fixture(office)
    monkeypatch.setenv("apple_flow_admin_api_token", "secret-token")
    monkeypatch.setenv("apple_flow_soul_file", str(office / "SOUL.md"))

    app = build_app(store=InMemoryStore())
    client = TestClient(app)

    assert client.post("/dashboard/api/companion/mute").status_code == 401
    assert client.post("/dashboard/api/companion/unmute").status_code == 401


def test_dashboard_companion_actions_toggle_store_state(monkeypatch, tmp_path):
    office = tmp_path / "agent-office"
    _write_agent_office_fixture(office)
    monkeypatch.setenv("apple_flow_admin_api_token", "secret-token")
    monkeypatch.setenv("apple_flow_soul_file", str(office / "SOUL.md"))

    store = InMemoryStore()
    app = build_app(store=store)
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret-token"}

    mute_response = client.post("/dashboard/api/companion/mute", headers=headers)
    assert mute_response.status_code == 200
    assert mute_response.json() == {"companion_muted": True}
    assert store.get_state("companion_muted") == "true"

    unmute_response = client.post("/dashboard/api/companion/unmute", headers=headers)
    assert unmute_response.status_code == 200
    assert unmute_response.json() == {"companion_muted": False}
    assert store.get_state("companion_muted") == "false"
