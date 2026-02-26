"""Agent-office → Supabase sync layer.

Parses markdown files in agent-office/ and upserts rows into local Supabase
tables via the PostgREST REST API. Markdown stays primary; Supabase is the
queryable backup layer.

Tables synced:
  automation_runs   ← 90_logs/automation-log.md
  memory_entries    ← MEMORY.md + 60_memory/*.md
  daily_notes       ← 10_daily/YYYY-MM-DD.md
  inbox_items       ← 00_inbox/inbox.md
  projects          ← 20_projects/*/brief.md
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("apple_flow.office_sync")

# UUID5 namespace for all office sync IDs
_NS = uuid.NAMESPACE_OID

# Automation log line pattern:
# "- YYYY-MM-DD HH:MM | schedule(...) | action | result | notes"
# OR "- YYYY-MM-DD HH:MM | companion | action | ..."
_LOG_LINE_RE = re.compile(r"^-\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+\|\s+(.+)$")


class OfficeSyncer:
    """Sync agent-office markdown files to local Supabase tables."""

    def __init__(self, office_path: Path, supabase_url: str, service_key: str):
        self.office_path = office_path
        self.supabase_url = supabase_url.rstrip("/")
        self.service_key = service_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_all(self) -> dict[str, int]:
        """Sync all tables. Returns {table: rows_upserted}."""
        results: dict[str, int] = {}
        for name, method in [
            ("automation_runs", self._sync_automation_log),
            ("memory_entries", self._sync_memory),
            ("daily_notes", self._sync_daily_notes),
            ("inbox_items", self._sync_inbox),
            ("projects", self._sync_projects),
        ]:
            try:
                n = method()
                results[name] = n
                logger.debug("Synced %s: %d rows", name, n)
            except Exception as exc:
                logger.warning("Failed to sync %s: %s", name, exc)
                results[name] = 0
        return results

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _sync_automation_log(self) -> int:
        log_path = self.office_path / "90_logs" / "automation-log.md"
        if not log_path.exists():
            return 0

        rows: list[dict[str, Any]] = []
        content = log_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            m = _LOG_LINE_RE.match(line)
            if not m:
                continue
            run_at_str, rest = m.group(1), m.group(2)
            parts = [p.strip() for p in rest.split("|")]

            # Need at least: schedule_type | action | result
            if len(parts) < 3:
                continue

            schedule_type = parts[0]  # e.g. "schedule(manual)" or "companion"
            action = parts[1]
            result = parts[2]
            notes = parts[3] if len(parts) > 3 else ""

            try:
                run_at = datetime.strptime(run_at_str.strip(), "%Y-%m-%d %H:%M").isoformat()
            except ValueError:
                continue

            row_id = self._uuid5_id(run_at, action)
            rows.append(
                {
                    "id": row_id,
                    "run_at": run_at,
                    "schedule_type": schedule_type,
                    "action": action,
                    "result": result,
                    "notes": notes,
                }
            )

        return self._upsert("automation_runs", rows)

    def _sync_memory(self) -> int:
        rows: list[dict[str, Any]] = []

        # MEMORY.md — H2 sections → is_durable=True, topic="durable"
        memory_md = self.office_path / "MEMORY.md"
        if memory_md.exists():
            sections = self._parse_h2_sections(memory_md.read_text(encoding="utf-8"))
            for section, body in sections:
                row_id = self._uuid5_id("durable", section)
                rows.append(
                    {
                        "id": row_id,
                        "topic": "durable",
                        "section": section,
                        "content": body,
                        "is_durable": True,
                        "source": "MEMORY.md",
                    }
                )

        # 60_memory/*.md — topic=filename stem
        memory_dir = self.office_path / "60_memory"
        if memory_dir.exists():
            for md_file in sorted(memory_dir.glob("*.md")):
                topic = md_file.stem
                sections = self._parse_h2_sections(md_file.read_text(encoding="utf-8"))
                for section, body in sections:
                    row_id = self._uuid5_id(topic, section)
                    rows.append(
                        {
                            "id": row_id,
                            "topic": topic,
                            "section": section,
                            "content": body,
                            "is_durable": False,
                            "source": f"60_memory/{md_file.name}",
                        }
                    )

        return self._upsert("memory_entries", rows)

    def _sync_daily_notes(self) -> int:
        daily_dir = self.office_path / "10_daily"
        if not daily_dir.exists():
            return 0

        rows: list[dict[str, Any]] = []
        date_re = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
        for md_file in sorted(daily_dir.glob("*.md")):
            m = date_re.match(md_file.name)
            if not m:
                continue
            note_date = m.group(1)
            content = md_file.read_text(encoding="utf-8")
            sections = dict(self._parse_h2_sections(content))

            row: dict[str, Any] = {"id": self._uuid5_id(note_date), "date": note_date}

            # Map well-known section names to JSONB columns
            def _lines(key: str) -> list[str]:
                body = sections.get(key, "")
                return [
                    ln.lstrip("- ").strip()
                    for ln in body.splitlines()
                    if ln.strip().startswith("-")
                ]

            row["top_priorities"] = _lines("Top 3 Priorities") or _lines("Priorities")
            row["open_loops"] = _lines("Open Loops") or _lines("Open loops")
            row["calendar_items"] = (
                _lines("Calendar") or _lines("Today's calendar") or _lines("Schedule")
            )
            row["morning_briefing"] = (
                sections.get("Morning Briefing", "").strip()
                or sections.get("Inbox Triage", "").strip()
                or None
            )
            row["work_log"] = (
                sections.get("Work Log", "").strip() or sections.get("Log", "").strip() or None
            )
            row["memory_delta"] = (
                sections.get("Memory Delta", "").strip()
                or sections.get("Memory", "").strip()
                or None
            )
            row["wins"] = (
                sections.get("Wins", "").strip() or sections.get("Reflection", "").strip() or None
            )

            rows.append(row)

        return self._upsert("daily_notes", rows, conflict_column="date")

    def _sync_inbox(self) -> int:
        inbox_path = self.office_path / "00_inbox" / "inbox.md"
        if not inbox_path.exists():
            return 0

        rows: list[dict[str, Any]] = []
        # "- [ ] YYYY-MM-DD HH:MM | source | note" → untriaged
        # "- [x] ..."                               → archive
        line_re = re.compile(
            r"^-\s+\[([ x])\]\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*\|\s*([^|]*)\|\s*(.+)$",
            re.IGNORECASE,
        )
        content = inbox_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            m = line_re.match(line)
            if not m:
                continue
            checked, captured_at_str, source, note = m.groups()
            status = "archive" if checked.lower() == "x" else "untriaged"
            try:
                captured_at = datetime.strptime(
                    captured_at_str.strip(), "%Y-%m-%d %H:%M"
                ).isoformat()
            except ValueError:
                continue
            note_clean = note.strip()
            row_id = self._uuid5_id(captured_at, note_clean[:80])
            rows.append(
                {
                    "id": row_id,
                    "captured_at": captured_at,
                    "source": source.strip(),
                    "content": note_clean,
                    "status": status,
                }
            )

        return self._upsert("inbox_items", rows)

    def _sync_projects(self) -> int:
        projects_dir = self.office_path / "20_projects"
        if not projects_dir.exists():
            return 0

        rows: list[dict[str, Any]] = []
        for subdir in sorted(projects_dir.iterdir()):
            if not subdir.is_dir():
                continue
            brief_path = subdir / "brief.md"
            if not brief_path.exists():
                continue
            project_name = subdir.name
            content = brief_path.read_text(encoding="utf-8")
            sections = dict(self._parse_h2_sections(content))

            row_id = self._uuid5_id(project_name)
            row: dict[str, Any] = {
                "id": row_id,
                "project_name": project_name,
            }

            # Parse common brief fields
            row["status"] = sections.get("Status", "").strip() or None
            row["outcome"] = (
                sections.get("Outcome", "").strip()
                or sections.get("Success Criteria", "").strip()
                or None
            )
            row["why_now"] = (
                sections.get("Why Now", "").strip()
                or sections.get("Motivation", "").strip()
                or None
            )
            row["scope"] = (
                sections.get("Scope", "").strip() or sections.get("Scope In", "").strip() or None
            )
            row["scope_out"] = sections.get("Scope Out", "").strip() or None
            row["risks"] = (
                sections.get("Risks", "").strip() or sections.get("Blockers", "").strip() or None
            )

            rows.append(row)

        return self._upsert("projects", rows)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _upsert(self, table: str, rows: list[dict[str, Any]], conflict_column: str = "id") -> int:
        """POST rows to Supabase REST API with upsert-on-conflict."""
        if not rows:
            return 0

        url = f"{self.supabase_url}/rest/v1/{table}?on_conflict={conflict_column}"
        headers = {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        # PostgREST requires all objects in a batch to have identical keys.
        # Strip None values (so column defaults apply) and send one row at a time
        # to avoid PGRST102 when rows have different optional fields.
        succeeded = 0
        for row in rows:
            clean = {k: v for k, v in row.items() if v is not None}
            response = httpx.post(url, json=[clean], headers=headers, timeout=30.0)
            response.raise_for_status()
            succeeded += 1
        return succeeded

    @staticmethod
    def _uuid5_id(*parts: str) -> str:
        """Deterministic UUID5 ID from one or more string parts."""
        return str(uuid.uuid5(_NS, "|".join(parts)))

    @staticmethod
    def _parse_h2_sections(content: str) -> list[tuple[str, str]]:
        """Split markdown content into (heading, body) pairs for each H2 section."""
        sections: list[tuple[str, str]] = []
        current_heading: str | None = None
        body_lines: list[str] = []

        for line in content.splitlines():
            if line.startswith("## "):
                if current_heading is not None:
                    sections.append((current_heading, "\n".join(body_lines).strip()))
                current_heading = line[3:].strip()
                body_lines = []
            elif current_heading is not None:
                # Skip H1 titles and H3+ inside sections
                if not line.startswith("# "):
                    body_lines.append(line)

        if current_heading is not None:
            sections.append((current_heading, "\n".join(body_lines).strip()))

        return sections
