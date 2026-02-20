"""Ambient scanner — passively reads Apple apps for context enrichment.

Reads Notes, Calendar, and Mail broadly (all folders, all calendars) for
context enrichment without acting.  Writes observations to agent-office
memory files.  Never triggers actions or sends messages.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .memory import FileMemory

logger = logging.getLogger("apple_flow.ambient")


class AmbientScanner:
    """Passively scans Apple apps and writes context to memory files."""

    def __init__(
        self,
        memory: FileMemory,
        scan_interval_seconds: float = 900.0,
    ):
        self.memory = memory
        self.scan_interval_seconds = scan_interval_seconds

    async def run_forever(self, is_shutdown: Callable[[], bool]) -> None:
        """Main ambient scan loop."""
        logger.info("Ambient scanner started (interval=%.0fs)", self.scan_interval_seconds)
        while not is_shutdown():
            try:
                await asyncio.to_thread(self._scan)
            except Exception as exc:
                logger.exception("Ambient scan error: %s", exc)
            await asyncio.sleep(self.scan_interval_seconds)

    def _scan(self) -> None:
        """Run all ambient scans and update memory."""
        observations: list[str] = []

        notes_obs = self._scan_notes()
        observations.extend(notes_obs)

        calendar_obs = self._scan_calendar()
        observations.extend(calendar_obs)

        mail_obs = self._scan_mail_subjects()
        observations.extend(mail_obs)

        if observations:
            self._write_ambient_context(observations)

    def _scan_notes(self) -> list[str]:
        """Read recent notes across ALL folders for context."""
        observations: list[str] = []
        try:
            from . import apple_tools
            notes = apple_tools.notes_list(limit=20)
            if isinstance(notes, list):
                for note in notes:
                    name = note.get("name", "")
                    preview = (note.get("preview", "") or "")[:100]
                    if name:
                        observations.append(f"Note: {name} — {preview}")
        except Exception as exc:
            logger.debug("Ambient notes scan failed: %s", exc)
        return observations

    def _scan_calendar(self) -> list[str]:
        """Read upcoming events across ALL calendars for context."""
        observations: list[str] = []
        try:
            from . import apple_tools
            events = apple_tools.calendar_list_events(days_ahead=7, limit=20)
            if isinstance(events, list):
                for evt in events:
                    summary = evt.get("summary", "")
                    start = evt.get("start_date", "")
                    cal = evt.get("calendar", "")
                    if summary:
                        observations.append(f"Event: {summary} at {start} [{cal}]")
        except Exception as exc:
            logger.debug("Ambient calendar scan failed: %s", exc)
        return observations

    def _scan_mail_subjects(self) -> list[str]:
        """Read recent email subjects (not bodies) for topic awareness."""
        observations: list[str] = []
        try:
            from . import apple_tools
            messages = apple_tools.mail_list_unread(limit=10)
            if isinstance(messages, list):
                for msg in messages:
                    subject = msg.get("subject", "")
                    sender = msg.get("sender", "")
                    if subject:
                        observations.append(f"Email: {subject} from {sender}")
        except Exception as exc:
            logger.debug("Ambient mail scan failed: %s", exc)
        return observations

    def _write_ambient_context(self, observations: list[str]) -> None:
        """Write ambient observations to memory topic file."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        content = f"# Ambient Context\n\nLast Updated: {now_str}\n\n"
        for obs in observations:
            content += f"- {obs}\n"
        self.memory.write_topic("ambient-context", content)
        logger.info("Ambient scan wrote %d observations to memory", len(observations))
