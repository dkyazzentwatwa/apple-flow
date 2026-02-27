from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "agent-office" / "20_projects" / "workspace-dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))


def _load_module(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, DASHBOARD_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


snapshot = _load_module("snapshot.py", "workspace_dashboard_snapshot")
server_mod = _load_module("server.py", "workspace_dashboard_server_mod")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "agent-office"
    (root / "00_inbox").mkdir(parents=True)
    (root / "10_daily").mkdir(parents=True)
    (root / "20_projects").mkdir(parents=True)
    (root / "60_memory").mkdir(parents=True)
    (root / "80_automation").mkdir(parents=True)
    (root / "90_logs").mkdir(parents=True)

    (root / "MEMORY.md").write_text("## Active Goals\n- Ship dashboard\n", encoding="utf-8")
    (root / "10_daily" / "2026-02-25.md").write_text(
        "### Morning Briefing\nStatus check\n\n## Top 3 Priorities\n1) fix cache\n2) add runtime\n",
        encoding="utf-8",
    )
    (root / "00_inbox" / "inbox.md").write_text(
        "- [ ] 2026-02-25 09:10 | idea | Check dashboard\n",
        encoding="utf-8",
    )
    (root / "20_projects" / "demo").mkdir()
    (root / "20_projects" / "demo" / "brief.md").write_text("Demo summary", encoding="utf-8")
    return root


def test_extract_section_accepts_non_h2_heading() -> None:
    text = "### Top 3 Priorities\n1) one\n- two\n\n## Notes\nhello"
    section = snapshot._extract_section(text, "Top 3 Priorities")
    assert "one" in section
    assert "two" in section


def test_log_stats_reads_recent_tail(workspace: Path) -> None:
    log_path = workspace / "90_logs" / "automation-log.md"
    old_lines = "".join(
        f"- 2025-01-01 00:{i:02d} | schedule(auto) | action_{i} | success | old\n" for i in range(2000)
    )
    new_tail = (
        "- 2026-02-25 10:00 | schedule(manual) | important_action | success | new\n"
        "- 2026-02-25 10:02 | schedule(manual) | failing_action | error | new\n"
    )
    log_path.write_text(old_lines + new_tail, encoding="utf-8")

    stats = snapshot._log_stats(workspace)

    assert stats["exists"] is True
    assert stats["recent"][0]["action"] == "failing_action"
    assert stats["failure_count"] >= 1


def test_server_snapshot_cache_and_file_drilldown(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_snapshot(_workspace: Path) -> dict:
        calls["count"] += 1
        return {
            "generated_at": "2026-02-25T12:00:00+00:00",
            "workspace": {"name": "agent-office", "path": str(workspace)},
            "health_strip": {
                "daily_streak_days": 1,
                "projects_total": 1,
                "projects_missing_brief": 0,
                "projects_stale": 0,
                "inbox_pending": 1,
                "memory_topics": 0,
                "recent_failures": 0,
                "automation_files": 0,
            },
            "attention_queue": [],
            "timeline": [],
            "projects": {"projects": []},
            "daily": {"priorities": [], "streak_days": 1, "latest_date": "2026-02-25", "morning_brief": "", "latest_file": "10_daily/2026-02-25.md"},
            "inbox": {"pending_entries": 1},
            "memory": {"active_goals": [], "master_last_updated": "2026-02-25"},
            "logs": {"failure_count": 0},
            "freshness": {"daily": {"state": "fresh", "label": "0h old"}, "memory": {"state": "fresh", "label": "0d old"}},
        }

    monkeypatch.setattr(server_mod, "_build_workspace_snapshot", fake_snapshot)

    httpd = server_mod.DashboardHTTPServer.__new__(server_mod.DashboardHTTPServer)
    httpd.workspace_path = workspace
    httpd.links = []
    httpd.snapshot_ttl_seconds = 60
    httpd._snapshot_cache = None
    httpd._snapshot_cache_at = 0.0

    first = httpd.get_snapshot()
    second = httpd.get_snapshot()
    assert first["workspace"]["name"] == "agent-office"
    assert second["workspace"]["name"] == "agent-office"
    assert calls["count"] == 1

    handler = server_mod.DashboardHandler.__new__(server_mod.DashboardHandler)
    handler.server = httpd
    payload = handler._read_workspace_file("MEMORY.md")
    assert payload["ok"] is True
    assert "Ship dashboard" in payload["content"]
