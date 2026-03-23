from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from conftest import FakeStore

from apple_flow.dashboard import build_agent_office_summary


def test_build_agent_office_summary_reads_expected_agent_office_fixture(agent_office):
    store = FakeStore()
    config = SimpleNamespace()
    now = datetime(2026, 3, 22, 12, 0, tzinfo=UTC)

    summary = build_agent_office_summary(agent_office, store=store, config=config, now=now)

    assert summary["agent_office_path"] == str(agent_office)
    assert summary["generated_at"].startswith("2026-03-22T12:00:00")

    assert summary["inbox"]["unchecked_count"] == 2
    assert summary["inbox"]["exists"] is True
    assert "First inbox item" in summary["inbox"]["preview"]
    assert summary["inbox"]["modified_at"]

    assert summary["daily"]["today_exists"] is True
    assert summary["daily"]["today_path"].endswith("2026-03-22.md")
    assert "Morning Briefing" in summary["daily"]["preview"]

    assert summary["memory"]["topic_count"] == 2
    assert [topic["name"] for topic in summary["memory"]["topics"]] == [
        "project-alpha.md",
        "project-beta.md",
    ]
    assert "Important durable memory" in summary["memory"]["preview"]

    assert [item["name"] for item in summary["recent"]["outputs"]] == [
        "latest-output.md",
        "older-output.md",
    ]
    assert [item["name"] for item in summary["recent"]["resources"]] == [
        "library.md",
        "reference.md",
    ]
    assert [item["name"] for item in summary["recent"]["logs"]] == [
        "apple-flow.err.log",
        "apple-flow-admin.err.log",
        "apple-flow-admin.log",
        "apple-flow.log",
    ]
    assert summary["recent"]["outputs"][0]["preview"]
    assert summary["recent"]["resources"][0]["modified_at"]
    assert summary["recent"]["logs"][0]["modified_at"]
    assert "daemon err line 14" in summary["recent"]["logs"][0]["preview"]
    assert "daemon err line 2" not in summary["recent"]["logs"][0]["preview"]
    assert summary["recent"]["highlights"][0]["kind"] == "error"
    assert "timeout" in summary["recent"]["highlights"][0]["line"].lower()

    assert summary["inbox"]["freshness"]["state"] == "fresh"
    assert summary["daily"]["freshness"]["state"] == "fresh"
    assert summary["memory"]["freshness"]["state"] == "fresh"
    assert summary["recent"]["freshness"]["state"] == "fresh"
    assert summary["attention"]["count"] == 2
    assert [item["kind"] for item in summary["attention"]["items"]] == ["inbox", "error"]


def test_build_agent_office_summary_ignores_unknown_paths(agent_office):
    summary = build_agent_office_summary(agent_office, store=FakeStore(), config=SimpleNamespace())

    assert summary["memory"]["topic_count"] == 2
    assert "unrelated.txt" not in {item["name"] for item in summary["recent"]["outputs"]}
    assert "unrelated.txt" not in {item["name"] for item in summary["recent"]["resources"]}
    assert "unrelated.txt" not in {item["name"] for item in summary["recent"]["logs"]}
    assert "other.log" not in {item["name"] for item in summary["recent"]["logs"]}


def test_build_agent_office_summary_includes_runtime_and_companion_state(agent_office):
    store = FakeStore()
    store.create_approval(
        request_id="req-1",
        run_id="run-1",
        summary="Approval one",
        command_preview="do something",
        expires_at="2026-03-22T13:00:00+00:00",
        sender="+15551234567",
    )
    store.create_approval(
        request_id="req-2",
        run_id="run-2",
        summary="Approval two",
        command_preview="do something else",
        expires_at="2026-03-22T13:30:00+00:00",
        sender="+15551234567",
    )
    store.set_state("companion_muted", "true")
    store.set_state("companion_last_check_at", "2026-03-22T11:55:00+00:00")
    store.set_state("companion_last_sent_at", "2026-03-22T11:56:00+00:00")
    store.set_state("companion_last_skip_reason", "quiet_hours")
    store.set_state("companion_proactive_hour_count", "3")

    summary = build_agent_office_summary(agent_office, store=store, config=SimpleNamespace())

    assert summary["runtime"]["pending_approvals_count"] == 2
    assert summary["companion"]["muted"] is True
    assert summary["companion"]["last_check_at"] == "2026-03-22T11:55:00+00:00"
    assert summary["companion"]["last_sent_at"] == "2026-03-22T11:56:00+00:00"
    assert summary["companion"]["skip_reason"] == "quiet_hours"
    assert summary["companion"]["proactive_hour_count"] == "3"


def test_build_agent_office_summary_counts_entries_section_only(tmp_path):
    office = tmp_path / "agent-office"
    inbox_dir = office / "00_inbox"
    inbox_dir.mkdir(parents=True)
    (office / "10_daily").mkdir()
    (office / "60_memory").mkdir()
    (office / "30_outputs").mkdir()
    (office / "40_resources").mkdir()
    (office / "90_logs").mkdir()

    (inbox_dir / "inbox.md").write_text(
        "# Inbox\n\n"
        "## Entry Format\n"
        "- [ ] Example task one\n"
        "- [ ] Example task two\n\n"
        "## Entries\n"
        "- [ ] Real inbox item one\n"
        "- [ ] Real inbox item two\n"
        "- [x] Completed inbox item\n",
        encoding="utf-8",
    )

    summary = build_agent_office_summary(office, store=FakeStore(), config=SimpleNamespace())

    assert summary["inbox"]["unchecked_count"] == 2
