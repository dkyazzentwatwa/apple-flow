"""Tests for office_sync.py — agent-office → Supabase sync layer."""

from __future__ import annotations

import textwrap
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apple_flow.office_sync import OfficeSyncer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def office(tmp_path: Path) -> Path:
    """Create a minimal agent-office directory structure."""
    (office := tmp_path / "agent-office").mkdir()
    (office / "90_logs").mkdir()
    (office / "60_memory").mkdir()
    (office / "10_daily").mkdir()
    (office / "00_inbox").mkdir()
    (office / "20_projects").mkdir()
    return office


@pytest.fixture
def syncer(office: Path) -> OfficeSyncer:
    return OfficeSyncer(
        office_path=office,
        supabase_url="http://localhost:54321",
        service_key="test-service-key",
    )


# ---------------------------------------------------------------------------
# UUID5 determinism
# ---------------------------------------------------------------------------


def test_uuid5_id_is_deterministic():
    a = OfficeSyncer._uuid5_id("topic", "section")
    b = OfficeSyncer._uuid5_id("topic", "section")
    assert a == b


def test_uuid5_id_differs_for_different_parts():
    a = OfficeSyncer._uuid5_id("topic", "section-a")
    b = OfficeSyncer._uuid5_id("topic", "section-b")
    assert a != b


def test_uuid5_id_is_valid_uuid():
    result = OfficeSyncer._uuid5_id("foo", "bar")
    # Should not raise
    uuid.UUID(result)


# ---------------------------------------------------------------------------
# H2 section parser
# ---------------------------------------------------------------------------


def test_parse_h2_sections_basic():
    content = textwrap.dedent("""\
        # Title

        ## Section A
        line 1
        line 2

        ## Section B
        line 3
    """)
    sections = OfficeSyncer._parse_h2_sections(content)
    assert len(sections) == 2
    assert sections[0][0] == "Section A"
    assert "line 1" in sections[0][1]
    assert sections[1][0] == "Section B"


def test_parse_h2_sections_empty_file():
    sections = OfficeSyncer._parse_h2_sections("")
    assert sections == []


def test_parse_h2_sections_no_h2():
    content = "# Only H1\nsome content\n"
    sections = OfficeSyncer._parse_h2_sections(content)
    assert sections == []


# ---------------------------------------------------------------------------
# Automation log parser
# ---------------------------------------------------------------------------


def test_sync_automation_log_valid_lines(office: Path, syncer: OfficeSyncer):
    log_path = office / "90_logs" / "automation-log.md"
    log_path.write_text(
        "# Automation Log\n\n"
        "## Run Format\n- YYYY-MM-DD HH:MM | schedule(...) | action | result | notes\n\n"
        "## Runs\n"
        "- 2026-02-18 15:56 | schedule(manual) | scrape crexi | completed | found 10 listings\n"
        "- 2026-02-18 18:00 | schedule(daily) | end-of-day routine | completed | done\n"
    )

    rows: list[dict] = []

    def mock_upsert(table, r, **kwargs):
        rows.extend(r)
        return len(r)

    syncer._upsert = mock_upsert  # type: ignore[assignment]
    count = syncer._sync_automation_log()
    assert count == 2
    assert rows[0]["action"] == "scrape crexi"
    assert rows[0]["schedule_type"] == "schedule(manual)"
    assert rows[0]["result"] == "completed"
    assert rows[0]["notes"] == "found 10 listings"
    assert rows[1]["schedule_type"] == "schedule(daily)"


def test_sync_automation_log_skips_header_lines(office: Path, syncer: OfficeSyncer):
    log_path = office / "90_logs" / "automation-log.md"
    log_path.write_text(
        "# Automation Log\n"
        "## Run Format\n"
        "- YYYY-MM-DD HH:MM | schedule(...) | action | result | notes\n"
        "Some header text without pipes.\n"
        "- 2026-02-19 09:00 | schedule(manual) | real action | completed | ok\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_automation_log()
    assert count == 1
    assert rows[0]["action"] == "real action"


def test_sync_automation_log_malformed_lines_skipped(office: Path, syncer: OfficeSyncer):
    log_path = office / "90_logs" / "automation-log.md"
    log_path.write_text(
        "- not a valid log line\n"
        "- 2026-02-16 20:16 Created folder without pipe separator\n"
        "- 2026-02-19 10:00 | schedule(manual) | action | result\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_automation_log()
    assert count == 1  # Only the last line is valid


def test_sync_automation_log_companion_lines(office: Path, syncer: OfficeSyncer):
    log_path = office / "90_logs" / "automation-log.md"
    log_path.write_text(
        "- 2026-02-18 21:48 | companion | observation | 3 obs | quick check\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    syncer._sync_automation_log()
    assert rows[0]["schedule_type"] == "companion"
    assert rows[0]["action"] == "observation"


def test_sync_automation_log_missing_file(office: Path, syncer: OfficeSyncer):
    count = syncer._sync_automation_log()
    assert count == 0


# ---------------------------------------------------------------------------
# Memory parser
# ---------------------------------------------------------------------------


def test_sync_memory_durable(office: Path, syncer: OfficeSyncer):
    (office / "MEMORY.md").write_text(
        "# Memory\n\n## Rebrand\npackage renamed to apple-flow\n\n## Key Facts\nPython 3.11\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_memory()
    assert count == 2
    topics = {r["topic"] for r in rows}
    assert topics == {"durable"}
    sections = {r["section"] for r in rows}
    assert "Rebrand" in sections
    assert "Key Facts" in sections
    assert all(r["is_durable"] for r in rows)


def test_sync_memory_topic_files(office: Path, syncer: OfficeSyncer):
    (office / "60_memory" / "projects.md").write_text(
        "## Sub-agent routing\ndesign doc in 20_projects\n"
    )
    (office / "60_memory" / "tools.md").write_text(
        "## Apple integration\nNotes, Reminders, Calendar, Mail\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_memory()
    assert count == 2
    assert not any(r["is_durable"] for r in rows)
    topics = {r["topic"] for r in rows}
    assert "projects" in topics
    assert "tools" in topics


def test_sync_memory_no_files(office: Path, syncer: OfficeSyncer):
    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_memory()
    assert count == 0


# ---------------------------------------------------------------------------
# Daily notes parser
# ---------------------------------------------------------------------------


def test_sync_daily_notes_parses_sections(office: Path, syncer: OfficeSyncer):
    note_path = office / "10_daily" / "2026-02-19.md"
    note_path.write_text(
        "# Daily Note — 2026-02-19\n\n"
        "## Top 3 Priorities\n- Ship office sync\n- Review tests\n\n"
        "## Wins\n- Got 18 tasks done\n\n"
        "## Morning Briefing\nAll clear.\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_daily_notes()
    assert count == 1
    row = rows[0]
    assert row["date"] == "2026-02-19"
    assert "Ship office sync" in row["top_priorities"]
    assert "Got 18 tasks done" in row["wins"]
    assert row["morning_briefing"] == "All clear."


def test_sync_daily_notes_upserts_on_date(office: Path, syncer: OfficeSyncer):
    """Conflict column should be 'date' not 'id'."""
    (office / "10_daily" / "2026-02-19.md").write_text("# Note\n")

    conflict_col: list[str] = []
    def mock_upsert(table, rows, conflict_column="id"):
        conflict_col.append(conflict_column)
        return len(rows)

    syncer._upsert = mock_upsert  # type: ignore[assignment]
    syncer._sync_daily_notes()
    assert conflict_col == ["date"]


def test_sync_daily_notes_skips_non_date_files(office: Path, syncer: OfficeSyncer):
    (office / "10_daily" / "README.md").write_text("# Not a daily note\n")
    (office / "10_daily" / "2026-02-19.md").write_text("# Daily\n")

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_daily_notes()
    assert count == 1


# ---------------------------------------------------------------------------
# Inbox parser
# ---------------------------------------------------------------------------


def test_sync_inbox_unchecked_is_untriaged(office: Path, syncer: OfficeSyncer):
    inbox = office / "00_inbox" / "inbox.md"
    inbox.write_text(
        "## Entries\n"
        "- [ ] 2026-02-18 16:58 | apple-notes | Apple Notes 'Next level' note captured\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_inbox()
    assert count == 1
    assert rows[0]["status"] == "untriaged"
    assert rows[0]["source"] == "apple-notes"


def test_sync_inbox_checked_is_archive(office: Path, syncer: OfficeSyncer):
    inbox = office / "00_inbox" / "inbox.md"
    inbox.write_text(
        "- [x] 2026-02-19 09:08 | companion | stale carry-forward item archived\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    syncer._sync_inbox()
    assert rows[0]["status"] == "archive"


def test_sync_inbox_skips_non_checklist_lines(office: Path, syncer: OfficeSyncer):
    inbox = office / "00_inbox" / "inbox.md"
    inbox.write_text(
        "# Inbox\n"
        "## Entry Format\n"
        "- [ ] YYYY-MM-DD HH:MM | source | note\n"  # template line (no valid date)
        "## Entries\n"
        "- [ ] 2026-02-19 10:00 | test | real item\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_inbox()
    assert count == 1
    assert rows[0]["content"] == "real item"


def test_sync_inbox_missing_file(office: Path, syncer: OfficeSyncer):
    count = syncer._sync_inbox()
    assert count == 0


# ---------------------------------------------------------------------------
# Projects parser
# ---------------------------------------------------------------------------


def test_sync_projects_parses_brief(office: Path, syncer: OfficeSyncer):
    proj_dir = office / "20_projects" / "sub-agent-routing"
    proj_dir.mkdir()
    (proj_dir / "brief.md").write_text(
        "# Sub-agent Routing\n\n"
        "## Status\nin progress\n\n"
        "## Outcome\nrouting works for 5 agent personas\n\n"
        "## Scope\niMessage + Notes ingress only\n"
    )

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_projects()
    assert count == 1
    row = rows[0]
    assert row["project_name"] == "sub-agent-routing"
    assert row["status"] == "in progress"
    assert "5 agent personas" in row["outcome"]
    assert "iMessage" in row["scope"]


def test_sync_projects_no_brief_skipped(office: Path, syncer: OfficeSyncer):
    proj_dir = office / "20_projects" / "no-brief"
    proj_dir.mkdir()
    # No brief.md

    rows: list[dict] = []
    syncer._upsert = lambda table, r, **kw: (rows.extend(r), len(r))[1]  # type: ignore
    count = syncer._sync_projects()
    assert count == 0


def test_sync_projects_missing_dir(office: Path, syncer: OfficeSyncer):
    import shutil
    shutil.rmtree(office / "20_projects")
    count = syncer._sync_projects()
    assert count == 0


# ---------------------------------------------------------------------------
# sync_all
# ---------------------------------------------------------------------------


def test_sync_all_returns_table_counts(office: Path, syncer: OfficeSyncer):
    """sync_all with mocked _upsert — verifies all 5 tables are attempted."""
    (office / "90_logs" / "automation-log.md").write_text(
        "- 2026-02-19 10:00 | schedule(manual) | action | result | notes\n"
    )
    (office / "MEMORY.md").write_text("## Key\nvalue\n")
    (office / "10_daily" / "2026-02-19.md").write_text("# Day\n")
    (office / "00_inbox" / "inbox.md").write_text(
        "- [ ] 2026-02-19 10:00 | test | item\n"
    )
    proj_dir = office / "20_projects" / "alpha"
    proj_dir.mkdir()
    (proj_dir / "brief.md").write_text("## Status\nactive\n")

    upserted: dict[str, int] = {}

    def mock_upsert(table, rows, conflict_column="id"):
        upserted[table] = len(rows)
        return len(rows)

    syncer._upsert = mock_upsert  # type: ignore[assignment]
    result = syncer.sync_all()

    assert set(result.keys()) == {"automation_runs", "memory_entries", "daily_notes", "inbox_items", "projects"}
    assert result["automation_runs"] == 1
    assert result["memory_entries"] == 1
    assert result["daily_notes"] == 1
    assert result["inbox_items"] == 1
    assert result["projects"] == 1


def test_sync_all_continues_on_partial_failure(office: Path, syncer: OfficeSyncer):
    """If one table fails, the rest should still be attempted."""
    call_count = [0]

    def mock_upsert(table, rows, conflict_column="id"):
        call_count[0] += 1
        if table == "automation_runs":
            raise RuntimeError("simulated failure")
        return len(rows)

    syncer._upsert = mock_upsert  # type: ignore[assignment]
    result = syncer.sync_all()
    # All 5 tables attempted, automation_runs returns 0 on error
    assert result["automation_runs"] == 0
    assert set(result.keys()) == {"automation_runs", "memory_entries", "daily_notes", "inbox_items", "projects"}


# ---------------------------------------------------------------------------
# HTTP upsert (mocked httpx)
# ---------------------------------------------------------------------------


def test_upsert_sends_correct_headers(syncer: OfficeSyncer):
    rows = [{"id": "abc", "value": "x"}]
    captured: dict = {}

    def mock_post(url, json, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        return resp

    with patch("apple_flow.office_sync.httpx.post", side_effect=mock_post):
        n = syncer._upsert("my_table", rows)

    assert n == 1
    assert "my_table" in captured["url"]
    assert "on_conflict=id" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer test-service-key"
    assert captured["headers"]["apikey"] == "test-service-key"
    assert "merge-duplicates" in captured["headers"]["Prefer"]


def test_upsert_empty_rows_returns_zero(syncer: OfficeSyncer):
    n = syncer._upsert("any_table", [])
    assert n == 0


def test_upsert_raises_on_http_error(syncer: OfficeSyncer):
    rows = [{"id": "x"}]

    def mock_post(url, json, headers, timeout):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "bad request"
        raise httpx.HTTPStatusError("error", request=MagicMock(), response=resp)

    with patch("apple_flow.office_sync.httpx.post", side_effect=mock_post):
        with pytest.raises(httpx.HTTPStatusError):
            syncer._upsert("table", rows)
