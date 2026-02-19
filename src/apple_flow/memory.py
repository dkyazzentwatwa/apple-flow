"""File-based persistent memory using the agent-office workspace.

Instead of a SQLite memory table, memory lives in the filesystem:
- ``agent-office/MEMORY.md`` — durable top-level memory
- ``agent-office/60_memory/`` — topic-specific memory files

Files are transparent, user-editable, and git-versioned.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("apple_flow.memory")


class FileMemory:
    """Read/write memory stored in agent-office file structure."""

    def __init__(self, office_path: Path, max_context_chars: int = 2000):
        self.office_path = office_path
        self.memory_file = office_path / "MEMORY.md"
        self.memory_dir = office_path / "60_memory"
        self.max_context_chars = max_context_chars

    def read_durable(self) -> str:
        """Read MEMORY.md for injection into prompts."""
        if not self.memory_file.exists():
            return ""
        try:
            return self.memory_file.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.warning("Failed to read MEMORY.md: %s", exc)
            return ""

    def read_topic(self, topic: str) -> str:
        """Read a specific topic file from 60_memory/."""
        # Sanitize topic name for filesystem safety
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic)
        topic_file = self.memory_dir / f"{safe_name}.md"
        if not topic_file.exists():
            return ""
        try:
            return topic_file.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.warning("Failed to read topic %s: %s", topic, exc)
            return ""

    def list_topics(self) -> list[str]:
        """List all topic files in 60_memory/."""
        if not self.memory_dir.exists():
            return []
        try:
            return sorted(
                f.stem for f in self.memory_dir.glob("*.md")
                if f.stem != "intro"
            )
        except Exception:
            return []

    def update_durable(self, section: str, content: str) -> bool:
        """Update a section of MEMORY.md. Returns True on success."""
        if not self.memory_file.exists():
            return False
        try:
            text = self.memory_file.read_text(encoding="utf-8")
            section_header = f"## {section}"
            if section_header in text:
                # Find the section and the next section header
                start = text.index(section_header)
                rest = text[start + len(section_header):]
                next_section = rest.find("\n## ")
                if next_section >= 0:
                    end = start + len(section_header) + next_section
                    text = text[:start] + f"{section_header}\n{content}\n" + text[end:]
                else:
                    text = text[:start] + f"{section_header}\n{content}\n"
            else:
                text += f"\n{section_header}\n{content}\n"
            self.memory_file.write_text(text, encoding="utf-8")
            return True
        except Exception as exc:
            logger.warning("Failed to update MEMORY.md section %s: %s", section, exc)
            return False

    def write_topic(self, topic: str, content: str) -> bool:
        """Write a topic file to 60_memory/. Returns True on success."""
        if not self.memory_dir.exists():
            try:
                self.memory_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                return False
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic)
        topic_file = self.memory_dir / f"{safe_name}.md"
        try:
            topic_file.write_text(content, encoding="utf-8")
            return True
        except Exception as exc:
            logger.warning("Failed to write topic %s: %s", topic, exc)
            return False

    def get_context_for_prompt(self, query: str = "") -> str:
        """Build memory context string for prompt injection.

        Reads MEMORY.md and optionally relevant topic files, truncated to
        ``max_context_chars``.
        """
        parts: list[str] = []

        # Always include durable memory
        durable = self.read_durable()
        if durable:
            parts.append(durable)

        # If a query is provided, try to find relevant topic files
        if query:
            topics = self.list_topics()
            query_lower = query.lower()
            for topic in topics:
                if query_lower in topic.lower():
                    topic_content = self.read_topic(topic)
                    if topic_content:
                        parts.append(f"--- Topic: {topic} ---\n{topic_content}")

        combined = "\n\n".join(parts)
        if len(combined) > self.max_context_chars:
            combined = combined[:self.max_context_chars] + "\n[...truncated]"
        return combined
