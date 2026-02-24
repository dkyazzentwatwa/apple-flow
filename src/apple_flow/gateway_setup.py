from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnsureResult:
    """Result of ensuring a macOS Apple app resource."""

    status: str  # created | exists | failed
    detail: str = ""


@dataclass(frozen=True)
class GatewayResourceStatus:
    """Structured status for one ensured gateway resource."""

    label: str
    name: str
    result: EnsureResult


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_osascript(script: str, timeout_seconds: float = 12.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def _ensure_via_applescript(script: str) -> EnsureResult:
    try:
        result = _run_osascript(script)
        if result.returncode != 0:
            detail = (result.stderr or "").strip() or f"osascript exit code {result.returncode}"
            return EnsureResult(status="failed", detail=detail)
        marker = (result.stdout or "").strip().lower()
        if marker == "created":
            return EnsureResult(status="created")
        if marker == "exists":
            return EnsureResult(status="exists")
        if marker:
            return EnsureResult(status="failed", detail=f"unexpected output: {marker}")
        return EnsureResult(status="failed", detail="empty AppleScript output")
    except subprocess.TimeoutExpired:
        return EnsureResult(status="failed", detail="timed out")
    except FileNotFoundError:
        return EnsureResult(status="failed", detail="osascript not found (requires macOS)")
    except OSError as exc:
        return EnsureResult(status="failed", detail=f"os error: {exc}")


def ensure_reminders_list(list_name: str) -> EnsureResult:
    safe_name = _escape_applescript(list_name)
    script = (
        'tell application "Reminders"\n'
        f'  if not (exists list "{safe_name}") then\n'
        f'    make new list with properties {{name:"{safe_name}"}}\n'
        '    return "created"\n'
        "  else\n"
        '    return "exists"\n'
        "  end if\n"
        "end tell"
    )
    return _ensure_via_applescript(script)


def ensure_notes_folder(folder_name: str) -> EnsureResult:
    safe_name = _escape_applescript(folder_name)
    script = (
        'tell application "Notes"\n'
        f'  if not (exists folder "{safe_name}") then\n'
        f'    make new folder with properties {{name:"{safe_name}"}}\n'
        '    return "created"\n'
        "  else\n"
        '    return "exists"\n'
        "  end if\n"
        "end tell"
    )
    return _ensure_via_applescript(script)


def ensure_calendar(calendar_name: str) -> EnsureResult:
    safe_name = _escape_applescript(calendar_name)
    script = (
        'tell application "Calendar"\n'
        f'  if not (exists calendar "{safe_name}") then\n'
        f'    make new calendar with properties {{name:"{safe_name}"}}\n'
        '    return "created"\n'
        "  else\n"
        '    return "exists"\n'
        "  end if\n"
        "end tell"
    )
    return _ensure_via_applescript(script)


def ensure_gateway_resources(
    *,
    enable_reminders: bool,
    enable_notes: bool,
    enable_notes_logging: bool,
    enable_calendar: bool,
    reminders_list_name: str,
    reminders_archive_list_name: str,
    notes_folder_name: str,
    notes_archive_folder_name: str,
    notes_log_folder_name: str,
    calendar_name: str,
) -> list[GatewayResourceStatus]:
    statuses: list[GatewayResourceStatus] = []
    if enable_reminders:
        statuses.append(
            GatewayResourceStatus(
                label="Reminders task list",
                name=reminders_list_name,
                result=ensure_reminders_list(reminders_list_name),
            )
        )
        statuses.append(
            GatewayResourceStatus(
                label="Reminders archive list",
                name=reminders_archive_list_name,
                result=ensure_reminders_list(reminders_archive_list_name),
            )
        )
    if enable_notes:
        statuses.append(
            GatewayResourceStatus(
                label="Notes task folder",
                name=notes_folder_name,
                result=ensure_notes_folder(notes_folder_name),
            )
        )
        statuses.append(
            GatewayResourceStatus(
                label="Notes archive folder",
                name=notes_archive_folder_name,
                result=ensure_notes_folder(notes_archive_folder_name),
            )
        )
    if enable_notes_logging:
        statuses.append(
            GatewayResourceStatus(
                label="Notes log folder",
                name=notes_log_folder_name,
                result=ensure_notes_folder(notes_log_folder_name),
            )
        )
    if enable_calendar:
        statuses.append(
            GatewayResourceStatus(
                label="Calendar",
                name=calendar_name,
                result=ensure_calendar(calendar_name),
            )
        )
    return statuses


def resolve_binary(binary_name: str) -> str | None:
    """Resolve an executable path using PATH and common macOS locations."""
    found = shutil.which(binary_name)
    if found:
        return str(Path(found).expanduser().resolve())
    candidates = [
        Path.home() / ".local" / "bin" / binary_name,
        Path("/opt/homebrew/bin") / binary_name,
        Path("/usr/local/bin") / binary_name,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve())
    return None
