from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import apple_tools
from .osascript_utils import run_osascript_with_recovery


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
    app_name = ""
    if 'tell application "Reminders"' in script:
        app_name = "Reminders"
    elif 'tell application "Notes"' in script:
        app_name = "Notes"
    elif 'tell application "Calendar"' in script:
        app_name = "Calendar"

    result = run_osascript_with_recovery(
        script,
        app_name=app_name,
        timeout=12.0,
        max_attempts=3,
    )
    if not result.ok:
        return EnsureResult(status="failed", detail=result.detail)
    marker = result.stdout.strip().lower()
    if marker == "created":
        return EnsureResult(status="created")
    if marker == "exists":
        return EnsureResult(status="exists")
    if marker:
        return EnsureResult(status="failed", detail=f"unexpected output: {marker}")
    return EnsureResult(status="failed", detail="empty AppleScript output")


def ensure_reminders_list(list_name: str) -> EnsureResult:
    selector = (list_name or "").strip()
    path_parts = apple_tools.reminders_split_selector(selector)

    if len(path_parts) <= 1:
        safe_name = _escape_applescript(selector)
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

    resolved = apple_tools.reminders_resolve_list_selector(selector)
    if resolved is not None:
        return EnsureResult(status="exists")

    account_name = _escape_applescript(path_parts[0])
    list_literals = ", ".join(f'"{_escape_applescript(part)}"' for part in path_parts[1:])
    script = (
        'tell application "Reminders"\n'
        f'  set targetAccount to first account whose name is "{account_name}"\n'
        '  set pathParts to {' + list_literals + '}\n'
        '  set parentList to missing value\n'
        '  set createdAny to false\n'
        '  repeat with rawPart in pathParts\n'
        '    set partName to rawPart as text\n'
        '    if parentList is missing value then\n'
        '      set targetContainerId to id of targetAccount as text\n'
        '      try\n'
        '        set matchedList to first list whose name is partName and id of container is targetContainerId\n'
        '      on error\n'
        '        set matchedList to make new list at targetAccount with properties {name:partName}\n'
        '        set createdAny to true\n'
        '      end try\n'
        '    else\n'
        '      set targetContainerId to id of parentList as text\n'
        '      try\n'
        '        set matchedList to first list whose name is partName and id of container is targetContainerId\n'
        '      on error\n'
        '        set matchedList to make new list at parentList with properties {name:partName}\n'
        '        set createdAny to true\n'
        '      end try\n'
        '    end if\n'
        '    set parentList to matchedList\n'
        '  end repeat\n'
        '  if createdAny then\n'
        '    return "created"\n'
        '  end if\n'
        '  return "exists"\n'
        'end tell'
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
