from __future__ import annotations

from pathlib import Path


def _extract_section(markdown: str, heading: str) -> str:
    """Return the body under a markdown heading until the next heading."""
    target = heading.strip().lower()
    lines = markdown.splitlines()
    in_section = False
    collected: list[str] = []

    for line in lines:
        stripped = line.strip()
        is_heading = stripped.startswith("#")

        if is_heading:
            heading_text = stripped.lstrip("#").strip().lower()
            if in_section:
                break
            if heading_text == target:
                in_section = True
                continue

        if in_section:
            collected.append(line)

    return "\n".join(collected).strip()


def _is_failure_status(status: str) -> bool:
    normalized = status.strip().lower()
    success_values = {"ok", "success", "done", "completed", "passed"}
    if normalized in success_values:
        return False
    return "fail" in normalized or "error" in normalized


def _read_recent_text(path: Path, max_bytes: int = 131072) -> str:
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        if size <= max_bytes:
            fh.seek(0)
            data = fh.read()
            return data.decode("utf-8", errors="replace")

        fh.seek(-max_bytes, 2)
        data = fh.read()
        text = data.decode("utf-8", errors="replace")
        newline_index = text.find("\n")
        if newline_index >= 0:
            return text[newline_index + 1 :]
        return text


def _parse_log_line(line: str) -> dict[str, str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("- "):
        stripped = stripped[2:]

    parts = [part.strip() for part in stripped.split("|")]
    if len(parts) < 4:
        return None

    details = " | ".join(parts[4:]).strip() if len(parts) > 4 else ""
    return {
        "timestamp": parts[0],
        "schedule": parts[1],
        "action": parts[2],
        "status": parts[3],
        "details": details,
    }


def _log_stats(workspace: Path, recent_limit: int = 20) -> dict:
    log_path = workspace / "90_logs" / "automation-log.md"
    if not log_path.exists():
        return {"exists": False, "failure_count": 0, "recent": []}

    text = _read_recent_text(log_path)
    entries: list[dict[str, str]] = []
    failure_count = 0

    for line in text.splitlines():
        parsed = _parse_log_line(line)
        if not parsed:
            continue
        entries.append(parsed)
        if _is_failure_status(parsed["status"]):
            failure_count += 1

    recent = list(reversed(entries[-recent_limit:]))
    return {
        "exists": True,
        "failure_count": failure_count,
        "recent": recent,
    }
