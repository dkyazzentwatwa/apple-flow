from __future__ import annotations

from datetime import UTC, datetime
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_KNOWN_RECENT_DIRS = ("30_outputs", "40_resources", "90_logs")
_PREFERRED_LOG_FILES = (
    "apple-flow.err.log",
    "apple-flow-admin.err.log",
    "apple-flow-admin.log",
    "apple-flow.log",
)
_LOG_HIGHLIGHT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("error", re.compile(r"\b(ERROR|CRITICAL|EXCEPTION|FAILED|FAILURE)\b", re.IGNORECASE)),
    ("warning", re.compile(r"\b(WARN|WARNING|TIMEOUT|DENIED|SKIPPED)\b", re.IGNORECASE)),
    ("restart", re.compile(r"\b(restart|started server process|application startup complete|shutting down|kickstart)\b", re.IGNORECASE)),
    ("echo", re.compile(r"ignored probable outbound echo", re.IGNORECASE)),
)
_DASHBOARD_SECTIONS = {
    "inbox": "inbox",
    "daily": "daily",
    "memory": "memory",
    "recent": "recent",
    "runtime": "runtime",
    "companion": "companion",
}


def resolve_agent_office_path(soul_file: str | Path) -> Path:
    soul_path = Path(soul_file)
    if not soul_path.is_absolute():
        soul_path = Path(__file__).resolve().parents[2] / soul_path
    return soul_path.parent


def _coerce_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _iso_modified(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_age_label(age_seconds: float) -> str:
    if age_seconds < 60:
        return "just now"
    minutes = int(age_seconds // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = int(age_seconds // 3600)
    if hours < 24:
        return f"{hours}h ago"
    days = int(age_seconds // 86400)
    return f"{days}d ago"


def _freshness_payload(
    modified_at: str | None,
    now: datetime,
    *,
    fresh_seconds: float,
    quiet_seconds: float,
) -> dict[str, Any]:
    parsed = _parse_iso_datetime(modified_at)
    if parsed is None:
        return {"state": "stale", "age_seconds": None, "age_label": "not updated"}

    age_seconds = max(0.0, (now - parsed).total_seconds())
    if age_seconds <= fresh_seconds:
        state = "fresh"
    elif age_seconds <= quiet_seconds:
        state = "quiet"
    else:
        state = "stale"
    return {
        "state": state,
        "age_seconds": int(age_seconds),
        "age_label": _format_age_label(age_seconds),
    }


def _preview_text(path: Path, *, max_chars: int = 180) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    normalized = text.replace("\r\n", "\n").strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _read_detail_text(path: Path, *, max_chars: int = 24000) -> tuple[str, bool]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "", False
    normalized = text.replace("\r\n", "\n").rstrip()
    if len(normalized) <= max_chars:
        return normalized, False
    return normalized[: max_chars - 3].rstrip() + "...", True


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


def _tail_text(path: Path, *, line_limit: int = 12, char_limit: int = 800) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    tail = "\n".join(lines[-line_limit:]).strip()
    if len(tail) <= char_limit:
        return tail
    return "...\n" + tail[-(char_limit - 4):].lstrip()


def _project_logs_dir(office_path: Path) -> Path:
    return office_path.parent / "logs"


def _summarize_live_logs(office_path: Path, *, limit: int = 4) -> list[dict[str, Any]]:
    logs_dir = _project_logs_dir(office_path)
    if not logs_dir.exists():
        return []

    preferred_limit = min(limit, len(_PREFERRED_LOG_FILES))
    selected: list[Path] = []
    for name in _PREFERRED_LOG_FILES:
        candidate = logs_dir / name
        if candidate.is_file():
            selected.append(candidate)
    if len(selected) < preferred_limit:
        extras = [
            path for path in logs_dir.iterdir()
            if path.is_file() and path.name not in {item.name for item in selected}
        ]
        extras.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
        selected.extend(extras[: max(0, preferred_limit - len(selected))])

    summaries: list[dict[str, Any]] = []
    for path in selected[:preferred_limit]:
        summaries.append({
            "name": path.name,
            "path": str(path),
            "modified_at": _iso_modified(path),
            "size_bytes": path.stat().st_size,
            "preview": _tail_text(path),
        })
    return summaries


def _extract_log_highlights(log_items: list[dict[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in log_items:
        preview = str(item.get("preview") or "")
        if not preview:
            continue
        for raw_line in preview.splitlines():
            line = raw_line.strip()
            if not line or line == "...":
                continue
            kind = ""
            for candidate_kind, pattern in _LOG_HIGHLIGHT_PATTERNS:
                if pattern.search(line):
                    kind = candidate_kind
                    break
            if not kind:
                continue
            key = (item.get("name", ""), line)
            if key in seen:
                continue
            seen.add(key)
            highlights.append({
                "kind": kind,
                "source": item.get("name", ""),
                "modified_at": item.get("modified_at") or None,
                "line": line,
            })
            if len(highlights) >= limit:
                return highlights

    return highlights


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


def _summarize_inbox(office_path: Path, *, now: datetime) -> dict[str, Any]:
    inbox_path = office_path / "00_inbox" / "inbox.md"
    if not inbox_path.exists():
        return {
            "exists": False,
            "path": str(inbox_path),
            "modified_at": None,
            "size_bytes": 0,
            "unchecked_count": 0,
            "preview": "",
            "freshness": _freshness_payload(None, now, fresh_seconds=86400.0, quiet_seconds=172800.0),
        }

    content = inbox_path.read_text(encoding="utf-8", errors="replace")
    unchecked_count = _count_untriaged_inbox_items(content)
    modified_at = _iso_modified(inbox_path)
    return {
        "exists": True,
        "path": str(inbox_path),
        "modified_at": modified_at,
        "size_bytes": inbox_path.stat().st_size,
        "unchecked_count": unchecked_count,
        "preview": _preview_text(inbox_path),
        "freshness": _freshness_payload(modified_at, now, fresh_seconds=86400.0, quiet_seconds=172800.0),
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
            "size_bytes": 0,
            "preview": "",
            "freshness": _freshness_payload(None, now, fresh_seconds=43200.0, quiet_seconds=172800.0),
        }
    modified_at = _iso_modified(today_path)
    return {
        "today_exists": True,
        "today_path": str(today_path),
        "modified_at": modified_at,
        "size_bytes": today_path.stat().st_size,
        "preview": _preview_text(today_path),
        "freshness": _freshness_payload(modified_at, now, fresh_seconds=43200.0, quiet_seconds=172800.0),
    }


def _project_now(now: datetime, timezone_name: str) -> datetime:
    tz_name = (timezone_name or "").strip()
    if not tz_name:
        return now
    try:
        return now.astimezone(ZoneInfo(tz_name))
    except Exception:
        return now


def _section_item_path(office_path: Path, section_name: str, item_name: str, *, now: datetime, bucket: str = "") -> Path:
    section = section_name.strip().lower()
    name = (item_name or "").strip()
    bucket_name = (bucket or "").strip().lower()

    if section == "inbox":
        return office_path / "00_inbox" / "inbox.md"

    if section == "daily":
        return office_path / "10_daily" / (name or f"{now.date().isoformat()}.md")

    if section == "memory":
        if not name or name == "MEMORY.md":
            return office_path / "MEMORY.md"
        return office_path / "60_memory" / name

    if section == "recent":
        recent_dirs = {
            "outputs": office_path / "30_outputs",
            "resources": office_path / "40_resources",
            "logs": office_path.parent / "logs",
        }
        if bucket_name in recent_dirs:
            return recent_dirs[bucket_name] / name
        for candidate in recent_dirs.values():
            path = candidate / name
            if path.exists():
                return path
        return office_path / name

    raise KeyError(section_name)


def _detail_title(section_name: str, path: Path, *, bucket: str = "") -> str:
    section = section_name.strip().lower()
    if section == "inbox":
        return "Inbox"
    if section == "daily":
        return f"Daily Note · {path.stem}"
    if section == "memory":
        if path.name == "MEMORY.md":
            return "Memory"
        return f"Memory Topic · {path.stem}"
    if section == "recent":
        bucket_name = (bucket or "").strip().lower()
        bucket_label = {
            "outputs": "Output",
            "resources": "Resource",
            "logs": "Log",
        }.get(bucket_name, "File")
        return f"{bucket_label} · {path.name}"
    return path.name


def _detail_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".csv":
        return "csv"
    if suffix in {".log", ".txt"}:
        return "text"
    return "text"


def build_agent_office_item_detail(
    office_path: str | Path,
    *,
    section: str,
    name: str = "",
    bucket: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    office = Path(office_path)
    current = _coerce_now(now)
    project_now = _project_now(current, "")
    path = _section_item_path(office, section, name, now=project_now, bucket=bucket)
    if not path.exists():
        raise KeyError(f"{section}:{bucket}:{name}")

    content, truncated = _read_detail_text(path)
    modified_at = _iso_modified(path)
    return {
        "section": section.strip().lower(),
        "bucket": bucket.strip().lower() or None,
        "name": path.name,
        "title": _detail_title(section, path, bucket=bucket),
        "path": str(path),
        "modified_at": modified_at,
        "modified_at_pacific": _project_now(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC), "America/Los_Angeles").isoformat(),
        "size_bytes": path.stat().st_size,
        "content": content,
        "content_truncated": truncated,
        "content_kind": _detail_kind(path),
        "preview": _preview_text(path, max_chars=240),
        "freshness": _freshness_payload(modified_at, current, fresh_seconds=43200.0, quiet_seconds=172800.0),
    }


def _summarize_memory(office_path: Path, *, now: datetime) -> dict[str, Any]:
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
    modified_at = _iso_modified(memory_file) if memory_file.exists() else None

    return {
        "path": str(memory_file),
        "exists": memory_file.exists(),
        "modified_at": modified_at,
        "size_bytes": memory_file.stat().st_size if memory_file.exists() else 0,
        "topic_count": len(topics),
        "topics": topics,
        "preview": preview,
        "freshness": _freshness_payload(modified_at, now, fresh_seconds=259200.0, quiet_seconds=1209600.0),
    }


def _build_attention(summary: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    pending = int(summary.get("runtime", {}).get("pending_approvals_count", 0) or 0)
    if pending > 0:
        items.append({
            "kind": "approval",
            "label": "Pending approvals",
            "value": pending,
            "detail": f"{pending} approval{'s' if pending != 1 else ''} waiting",
        })

    inbox = summary.get("inbox", {})
    unchecked = int(inbox.get("unchecked_count", 0) or 0)
    if unchecked > 0:
        items.append({
            "kind": "inbox",
            "label": "Inbox",
            "value": unchecked,
            "detail": f"{unchecked} unchecked item{'s' if unchecked != 1 else ''}",
        })

    daily = summary.get("daily", {})
    if not daily.get("today_exists"):
        items.append({
            "kind": "daily",
            "label": "Daily note",
            "value": "Missing",
            "detail": "Today's note has not been written yet",
        })
    elif daily.get("freshness", {}).get("state") == "stale":
        items.append({
            "kind": "daily",
            "label": "Daily note",
            "value": "Stale",
            "detail": f"Last updated {daily.get('freshness', {}).get('age_label', 'unknown')}",
        })

    for highlight in summary.get("recent", {}).get("highlights", [])[:3]:
        items.append({
            "kind": highlight.get("kind", "log"),
            "label": highlight.get("source", "log"),
            "value": highlight.get("kind", "log").title(),
            "detail": highlight.get("line", ""),
        })

    return {"count": len(items), "items": items[:4]}


def _newest_modified_at(items: list[dict[str, Any]]) -> str | None:
    newest: datetime | None = None
    newest_value: str | None = None
    for item in items:
        candidate = _parse_iso_datetime(item.get("modified_at"))
        if candidate is None:
            continue
        if newest is None or candidate > newest:
            newest = candidate
            newest_value = item.get("modified_at")
    return newest_value


def get_agent_office_section(summary: dict[str, Any], section_name: str) -> dict[str, Any]:
    section = section_name.strip().lower()
    if section not in _DASHBOARD_SECTIONS:
        raise KeyError(section_name)
    key = _DASHBOARD_SECTIONS[section]
    return {"section": section, "data": summary[key]}


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
    project_now = _project_now(current, getattr(config, "timezone", ""))

    recent = {
        name.split("_", 1)[1]: _list_recent_files(office / name, limit=recent_limit)
        for name in _KNOWN_RECENT_DIRS
    }
    recent["logs"] = _summarize_live_logs(office, limit=recent_limit)
    recent["highlights"] = _extract_log_highlights(recent["logs"])
    recent["freshness"] = _freshness_payload(
        _newest_modified_at(recent["logs"]),
        current,
        fresh_seconds=7200.0,
        quiet_seconds=43200.0,
    )

    summary = {
        "agent_office_path": str(office),
        "generated_at": current.isoformat(),
        "inbox": _summarize_inbox(office, now=current),
        "daily": _summarize_daily(office, now=project_now),
        "memory": _summarize_memory(office, now=current),
        "recent": recent,
        "runtime": _summarize_runtime(store),
        "companion": _summarize_companion(store),
    }
    summary["attention"] = _build_attention(summary)
    return summary
