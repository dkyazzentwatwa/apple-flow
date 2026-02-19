"""Tests for file-based memory (agent-office MEMORY.md + 60_memory/)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apple_flow.memory import FileMemory


@pytest.fixture
def office(tmp_path):
    """Set up a minimal agent-office structure."""
    (tmp_path / "MEMORY.md").write_text(
        "# Memory (Durable)\n\n## Identity\n- User prefers concise responses\n\n## Goals\n- Ship v2\n"
    )
    mem_dir = tmp_path / "60_memory"
    mem_dir.mkdir()
    (mem_dir / "intro.md").write_text("# 60_memory intro")
    (mem_dir / "deploy-history.md").write_text("# Deploy History\n\n- Deployed v1 on 2026-01-15\n")
    (mem_dir / "preferences.md").write_text("# Preferences\n\n- Dark mode\n- Vim keybindings\n")
    return tmp_path


class TestReadDurable:
    def test_reads_content(self, office):
        mem = FileMemory(office)
        content = mem.read_durable()
        assert "Identity" in content
        assert "concise responses" in content

    def test_returns_empty_when_missing(self, tmp_path):
        mem = FileMemory(tmp_path)
        assert mem.read_durable() == ""


class TestReadTopic:
    def test_reads_existing_topic(self, office):
        mem = FileMemory(office)
        content = mem.read_topic("deploy-history")
        assert "Deployed v1" in content

    def test_returns_empty_when_missing(self, office):
        mem = FileMemory(office)
        assert mem.read_topic("nonexistent") == ""

    def test_sanitizes_topic_name(self, office):
        mem = FileMemory(office)
        result = mem.read_topic("../../etc/passwd")
        assert result == ""


class TestListTopics:
    def test_lists_topics_excluding_intro(self, office):
        mem = FileMemory(office)
        topics = mem.list_topics()
        assert "deploy-history" in topics
        assert "preferences" in topics
        assert "intro" not in topics

    def test_returns_empty_when_no_dir(self, tmp_path):
        mem = FileMemory(tmp_path)
        assert mem.list_topics() == []


class TestUpdateDurable:
    def test_updates_existing_section(self, office):
        mem = FileMemory(office)
        assert mem.update_durable("Identity", "- User prefers verbose responses")
        content = mem.read_durable()
        assert "verbose responses" in content
        assert "Goals" in content

    def test_appends_new_section(self, office):
        mem = FileMemory(office)
        assert mem.update_durable("New Section", "- Something new")
        content = mem.read_durable()
        assert "New Section" in content
        assert "Something new" in content

    def test_returns_false_when_no_memory_file(self, tmp_path):
        mem = FileMemory(tmp_path)
        assert mem.update_durable("Test", "content") is False


class TestWriteTopic:
    def test_creates_new_topic(self, office):
        mem = FileMemory(office)
        assert mem.write_topic("new-topic", "# New Topic\n\n- Data")
        content = mem.read_topic("new-topic")
        assert "New Topic" in content

    def test_overwrites_existing_topic(self, office):
        mem = FileMemory(office)
        assert mem.write_topic("deploy-history", "# Updated\n\n- v2 deployed")
        content = mem.read_topic("deploy-history")
        assert "v2 deployed" in content

    def test_creates_dir_if_missing(self, tmp_path):
        mem = FileMemory(tmp_path)
        assert mem.write_topic("test", "content")
        assert (tmp_path / "60_memory" / "test.md").exists()


class TestGetContextForPrompt:
    def test_includes_durable_memory(self, office):
        mem = FileMemory(office)
        context = mem.get_context_for_prompt()
        assert "Identity" in context
        assert "concise responses" in context

    def test_truncates_to_max_chars(self, office):
        mem = FileMemory(office, max_context_chars=50)
        context = mem.get_context_for_prompt()
        assert len(context) <= 50 + len("\n[...truncated]")
        assert "truncated" in context

    def test_includes_matching_topics_with_query(self, office):
        mem = FileMemory(office)
        context = mem.get_context_for_prompt(query="deploy")
        assert "Deploy History" in context or "deploy" in context.lower()

    def test_empty_when_no_files(self, tmp_path):
        mem = FileMemory(tmp_path)
        assert mem.get_context_for_prompt() == ""
