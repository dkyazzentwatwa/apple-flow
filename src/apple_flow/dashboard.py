from __future__ import annotations

from datetime import UTC, datetime
import re
from pathlib import Path
from typing import Any

_KNOWN_RECENT_DIRS = ("30_outputs", "40_resources", "90_logs")


def _coerce_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _iso_modified(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _preview_text(path: Path, *, max_chars: int = 180) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    normalized = text.replace("\r\n", "\n").strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _summarize_file(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "path": str(path),
        "modified_at": _iso_modified(path),
        "size_bytes": path.stat().st_size,
        "preview": _preview_text(path),
    }


def _list_recent_files(directory: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    files = [path for path in directory.iterdir() if path.is_file()]
    files.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return [_summarize_file(path) for path in files[:limit]]


def _safe_pending_approvals_count(store: Any | None) -> int:
    if store is None or not hasattr(store, "list_pending_approvals"):
        return 0
    try:
        pending = store.list_pending_approvals()
    except Exception:
        return 0
    if not isinstance(pending, list):
        return 0
    return len(pending)


def _safe_state(store: Any | None, key: str, default: str = "") -> str:
    if store is None or not hasattr(store, "get_state"):
        return default
    try:
        value = store.get_state(key)
    except Exception:
        return default
    if value is None:
        return default
    return str(value)


def _summarize_runtime(store: Any | None) -> dict[str, Any]:
    pending_count = _safe_pending_approvals_count(store)
    return {
        "pending_approvals_count": pending_count,
    }


def _summarize_companion(store: Any | None) -> dict[str, Any]:
    muted = _safe_state(store, "companion_muted") == "true"
    last_check_at = _safe_state(store, "companion_last_check_at")
    last_sent_at = _safe_state(store, "companion_last_sent_at")
    skip_reason = _safe_state(store, "companion_last_skip_reason")
    hour_count = _safe_state(store, "companion_proactive_hour_count", "0")

    return {
        "muted": muted,
        "last_check_at": last_check_at or None,
        "last_sent_at": last_sent_at or None,
        "skip_reason": skip_reason,
        "proactive_hour_count": hour_count,
    }


def _summarize_inbox(office_path: Path) -> dict[str, Any]:
    inbox_path = office_path / "00_inbox" / "inbox.md"
    if not inbox_path.exists():
        return {
            "exists": False,
            "path": str(inbox_path),
            "modified_at": None,
            "unchecked_count": 0,
            "preview": "",
        }

    content = inbox_path.read_text(encoding="utf-8", errors="replace")
    unchecked_count = _count_untriaged_inbox_items(content)
    return {
        "exists": True,
        "path": str(inbox_path),
        "modified_at": _iso_modified(inbox_path),
        "unchecked_count": unchecked_count,
        "preview": _preview_text(inbox_path),
    }


def _count_untriaged_inbox_items(content: str) -> int:
    """Count unchecked markdown tasks in the real inbox entries section."""
    unchecked_pattern = re.compile(r"^\s*-\s\[\s\]\s+")
    lines = content.splitlines()

    in_entries = False
    saw_entries_header = False
    scoped_count = 0
    for raw_line in lines:
        line = raw_line.strip()
        if line.lower() == "## entries":
            saw_entries_header = True
            in_entries = True
            continue
        if in_entries and line.startswith("## "):
            in_entries = False
        if in_entries and unchecked_pattern.match(raw_line):
            scoped_count += 1

    if saw_entries_header:
        return scoped_count

    return sum(1 for line in lines if unchecked_pattern.match(line))


def _summarize_daily(office_path: Path, *, now: datetime) -> dict[str, Any]:
    daily_dir = office_path / "10_daily"
    today_path = daily_dir / f"{now.date().isoformat()}.md"
    if not today_path.exists():
        return {
            "today_exists": False,
            "today_path": str(today_path),
            "modified_at": None,
            "preview": "",
        }
    return {
        "today_exists": True,
        "today_path": str(today_path),
        "modified_at": _iso_modified(today_path),
        "preview": _preview_text(today_path),
    }


def _summarize_memory(office_path: Path) -> dict[str, Any]:
    memory_file = office_path / "MEMORY.md"
    memory_dir = office_path / "60_memory"
    topics: list[dict[str, Any]] = []

    if memory_dir.exists():
        for path in memory_dir.glob("*.md"):
            if path.name in {"intro.md", "MEMORY.md"}:
                continue
            if not path.is_file():
                continue
            topics.append(_summarize_file(path))
        topics.sort(key=lambda item: (item["modified_at"], item["name"]), reverse=True)

    preview = ""
    if memory_file.exists():
        preview = _preview_text(memory_file)

    return {
        "path": str(memory_file),
        "exists": memory_file.exists(),
        "modified_at": _iso_modified(memory_file) if memory_file.exists() else None,
        "topic_count": len(topics),
        "topics": topics,
        "preview": preview,
    }


def build_agent_office_summary(
    office_path: str | Path,
    *,
    store: Any | None = None,
    config: Any | None = None,
    now: datetime | None = None,
    recent_limit: int = 5,
) -> dict[str, Any]:
    office = Path(office_path)
    current = _coerce_now(now)

    recent = {
        name.split("_", 1)[1]: _list_recent_files(office / name, limit=recent_limit)
        for name in _KNOWN_RECENT_DIRS
    }

    return {
        "agent_office_path": str(office),
        "generated_at": current.isoformat(),
        "inbox": _summarize_inbox(office),
        "daily": _summarize_daily(office, now=current),
        "memory": _summarize_memory(office),
        "recent": recent,
        "runtime": _summarize_runtime(store),
        "companion": _summarize_companion(store),
    }
