"""Tests for the ambient scanner — passive context enrichment."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apple_flow.ambient import AmbientScanner  # noqa: E402
from apple_flow.memory import FileMemory  # noqa: E402


@pytest.fixture
def office(tmp_path):
    """Set up a minimal agent-office structure with memory dir."""
    (tmp_path / "MEMORY.md").write_text("# Memory\n")
    (tmp_path / "60_memory").mkdir()
    return tmp_path


@pytest.fixture
def memory(office):
    return FileMemory(office)


@pytest.fixture
def scanner(memory):
    return AmbientScanner(memory=memory, scan_interval_seconds=900.0)


class TestScanNotes:
    def test_returns_observations(self, scanner):
        with patch("apple_flow.apple_tools.notes_list", return_value=[
            {"name": "Meeting Notes", "preview": "Discussed Q2 plan"},
            {"name": "Shopping List", "preview": "Milk, eggs"},
        ]):
            obs = scanner._scan_notes()
        assert len(obs) == 2
        assert "Meeting Notes" in obs[0]

    def test_handles_empty(self, scanner):
        with patch("apple_flow.apple_tools.notes_list", return_value=[]):
            obs = scanner._scan_notes()
        assert obs == []

    def test_handles_exception(self, scanner):
        with patch("apple_flow.apple_tools.notes_list", side_effect=Exception("fail")):
            obs = scanner._scan_notes()
        assert obs == []


class TestScanCalendar:
    def test_returns_observations(self, scanner):
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[
            {"summary": "Team Standup", "start_date": "2026-02-18 09:00", "calendar": "Work"},
        ]):
            obs = scanner._scan_calendar()
        assert len(obs) == 1
        assert "Team Standup" in obs[0]

    def test_handles_empty(self, scanner):
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[]):
            obs = scanner._scan_calendar()
        assert obs == []


class TestScanMail:
    def test_returns_observations(self, scanner):
        with patch("apple_flow.apple_tools.mail_list_unread", return_value=[
            {"subject": "PR Review Needed", "sender": "dev@example.com"},
        ]):
            obs = scanner._scan_mail_subjects()
        assert len(obs) == 1
        assert "PR Review" in obs[0]

    def test_handles_empty(self, scanner):
        with patch("apple_flow.apple_tools.mail_list_unread", return_value=[]):
            obs = scanner._scan_mail_subjects()
        assert obs == []


class TestScan:
    def test_writes_ambient_context_to_memory(self, scanner, office):
        with patch("apple_flow.apple_tools.notes_list", return_value=[
            {"name": "Test Note", "preview": "Content"},
        ]), patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.mail_list_unread", return_value=[]):
            scanner._scan()

        topic_file = office / "60_memory" / "ambient-context.md"
        assert topic_file.exists()
        content = topic_file.read_text()
        assert "Test Note" in content
        assert "Ambient Context" in content

    def test_no_write_when_empty(self, scanner, office):
        with patch("apple_flow.apple_tools.notes_list", return_value=[]), \
             patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.mail_list_unread", return_value=[]):
            scanner._scan()

        topic_file = office / "60_memory" / "ambient-context.md"
        assert not topic_file.exists()


class TestRunForever:
    async def test_runs_and_stops(self, scanner):
        """Test that run_forever respects shutdown flag."""
        call_count = 0

        def mock_scan():
            nonlocal call_count
            call_count += 1

        scanner._scan = mock_scan
        scanner.scan_interval_seconds = 0.01

        import asyncio
        shutdown = False

        async def stop_after_short_delay():
            nonlocal shutdown
            await asyncio.sleep(0.05)
            shutdown = True

        await asyncio.gather(
            scanner.run_forever(lambda: shutdown),
            stop_after_short_delay(),
        )
        assert call_count >= 1
