"""Interactive setup wizard for Apple Flow.

Guides new users through configuring their .env file, validating inputs,
and auto-creating Apple app resources (Reminders lists, Notes folders,
Calendar calendars) via AppleScript.

Usage:
    python -m apple_flow setup
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Phone validation
# ---------------------------------------------------------------------------


def validate_phone(value: str) -> str | None:
    """Validate and clean an E.164 phone number.

    Accepts ``+`` followed by 7-15 digits.  Leading/trailing whitespace is
    stripped.  Returns the cleaned number or ``None`` if invalid.
    """
    cleaned = value.strip()
    if re.fullmatch(r"\+\d{7,15}", cleaned):
        return cleaned
    return None


# ---------------------------------------------------------------------------
# AppleScript helpers
# ---------------------------------------------------------------------------


def _escape_applescript(s: str) -> str:
    """Escape a string for safe embedding in an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def ensure_reminders_list(list_name: str) -> bool:
    """Create a Reminders list if it doesn't already exist.

    Returns ``True`` if the list was created, ``False`` if it already existed.
    """
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
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() == "created"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return False


def ensure_notes_folder(folder_name: str) -> bool:
    """Create a Notes folder if it doesn't already exist.

    Returns ``True`` if the folder was created, ``False`` if it already existed.
    """
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
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() == "created"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return False


def ensure_calendar(calendar_name: str) -> bool:
    """Create a Calendar if it doesn't already exist.

    Returns ``True`` if the calendar was created, ``False`` if it already existed.
    """
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
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() == "created"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return False


def check_full_disk_access() -> bool:
    """Check whether we can read the Messages database.

    Returns ``True`` if the file exists and is readable (which indicates
    Full Disk Access has been granted to the terminal).
    """
    db_path = Path.home() / "Library" / "Messages" / "chat.db"
    try:
        with db_path.open("rb") as f:
            f.read(16)
        return True
    except (PermissionError, FileNotFoundError, OSError):
        return False


# ---------------------------------------------------------------------------
# .env generation
# ---------------------------------------------------------------------------

_CONNECTOR_MAP = {
    "claude-cli": "claude-cli",
    "codex-cli": "codex-cli",
    "cline": "cline",
}


def generate_env(
    phone: str,
    connector: str,
    workspace: str,
    gateways: list[str],
    mail_address: str = "",
) -> str:
    """Generate the contents of a ``.env`` file from wizard answers.

    Only includes gateway-specific sections for the gateways the user selected.
    """
    lines: list[str] = [
        "# Generated by: python -m apple_flow setup",
        "# Edit freely — re-run the wizard at any time to regenerate.",
        "",
        "# --- Core ---",
        f"apple_flow_allowed_senders={phone}",
        f"apple_flow_default_workspace={workspace}",
        f"apple_flow_allowed_workspaces={workspace}",
        f"apple_flow_connector={connector}",
        "",
        "# --- Safety ---",
        "apple_flow_only_poll_allowed_senders=true",
        "apple_flow_require_chat_prefix=false",
        "apple_flow_approval_ttl_minutes=20",
        "apple_flow_max_messages_per_minute=30",
        "",
    ]

    if "mail" in gateways:
        lines += [
            "# --- Apple Mail ---",
            "apple_flow_enable_mail_polling=true",
            f"apple_flow_mail_allowed_senders={mail_address}",
            f"apple_flow_mail_from_address={mail_address}",
            "apple_flow_mail_poll_mailbox=INBOX",
            "",
        ]

    if "reminders" in gateways:
        lines += [
            "# --- Apple Reminders ---",
            "apple_flow_enable_reminders_polling=true",
            "apple_flow_reminders_list_name=agent-task",
            f"apple_flow_reminders_owner={phone}",
            "",
        ]

    if "notes" in gateways:
        lines += [
            "# --- Apple Notes ---",
            "apple_flow_enable_notes_polling=true",
            "apple_flow_notes_folder_name=agent-task",
            f"apple_flow_notes_owner={phone}",
            "",
        ]

    if "calendar" in gateways:
        lines += [
            "# --- Apple Calendar ---",
            "apple_flow_enable_calendar_polling=true",
            "apple_flow_calendar_name=agent-schedule",
            f"apple_flow_calendar_owner={phone}",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactive prompt helpers
# ---------------------------------------------------------------------------


def _ask(prompt: str, validate=None, default: str = "") -> str:
    """Prompt the user for input with optional validation.

    *validate* should be a callable that returns a cleaned value on success
    or ``None`` on failure.
    """
    while True:
        suffix = f" [{default}]" if default else ""
        try:
            raw = input(f"{prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            raise SystemExit(0)  # noqa: B904

        value = raw or default
        if not value:
            print("  A value is required.")
            continue
        if validate is not None:
            cleaned = validate(value)
            if cleaned is None:
                print("  Invalid input, please try again.")
                continue
            return cleaned
        return value


def _ask_choice(prompt: str, choices: list[str], multi: bool = False) -> str | list[str]:
    """Present a numbered menu and return the selected choice(s).

    When *multi* is ``True`` the user may enter comma-separated numbers or
    ``'a'`` for all.
    """
    for i, choice in enumerate(choices, 1):
        print(f"  {i}) {choice}")
    if multi:
        print("  a) All of the above")

    while True:
        try:
            raw = input(f"{prompt}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            raise SystemExit(0)  # noqa: B904

        if multi and raw == "a":
            return list(choices)

        parts = [p.strip() for p in raw.split(",")]
        selected: list[str] = []
        valid = True
        for part in parts:
            if not part.isdigit() or not (1 <= int(part) <= len(choices)):
                print(f"  Invalid selection: {part!r}")
                valid = False
                break
            selected.append(choices[int(part) - 1])
        if not valid:
            continue

        if not selected:
            print("  Please select at least one option.")
            continue

        if multi:
            return selected
        return selected[0]


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------

_CONNECTORS = [
    ("claude-cli", "Claude Code CLI (recommended)"),
    ("codex-cli", "Codex CLI"),
    ("cline", "Cline CLI (any model provider)"),
]

_GATEWAYS = ["mail", "reminders", "notes", "calendar"]


def run_wizard() -> None:
    """Run the interactive setup wizard."""
    print()
    print("=" * 56)
    print("  Apple Flow — Setup Wizard")
    print("=" * 56)
    print()
    print("This wizard will generate a .env configuration file.")
    print("You can re-run it at any time with: python -m apple_flow setup")
    print()

    # 1. Phone number
    phone = _ask(
        "Your phone number (E.164, e.g. +15551234567)",
        validate=validate_phone,
    )

    # 2. Connector
    print("\nWhich AI connector?")
    connector_labels = [label for _, label in _CONNECTORS]
    choice = _ask_choice("Select", connector_labels)
    connector = next(key for key, label in _CONNECTORS if label == choice)

    # 3. Workspace
    default_ws = str(Path.home())
    workspace = _ask("Default workspace path", default=default_ws)
    workspace = str(Path(workspace).expanduser().resolve())

    # 4. Gateways
    print("\nWhich Apple app gateways to enable?")
    gateways: list[str] = _ask_choice("Select (comma-separated, or 'a' for all)", _GATEWAYS, multi=True)  # type: ignore[assignment]

    # 5. Mail address
    mail_address = ""
    if "mail" in gateways:
        mail_address = _ask("Your email address (for Apple Mail)")

    # 6. Auto-create Apple app resources
    print()
    for gw in gateways:
        if gw == "reminders":
            print("  Creating Reminders list 'agent-task'...", end=" ")
            created = ensure_reminders_list("agent-task")
            print("done (created)" if created else "already exists")
        elif gw == "notes":
            print("  Creating Notes folder 'agent-task'...", end=" ")
            created = ensure_notes_folder("agent-task")
            print("done (created)" if created else "already exists")
        elif gw == "calendar":
            print("  Creating Calendar 'agent-schedule'...", end=" ")
            created = ensure_calendar("agent-schedule")
            print("done (created)" if created else "already exists")

    # 7. Generate and write .env
    env_content = generate_env(phone, connector, workspace, gateways, mail_address)

    env_path = Path(".env")
    if env_path.exists():
        overwrite = _ask(f"\n{env_path} already exists. Overwrite?", default="y")
        if overwrite.lower() not in ("y", "yes"):
            print("Skipped writing .env — here's what would have been written:\n")
            print(env_content)
            return

    env_path.write_text(env_content)
    print(f"\n  Wrote {env_path.resolve()}")

    # 8. Check Full Disk Access
    print("\nChecking Full Disk Access...")
    if check_full_disk_access():
        print("  Full Disk Access is granted.")
    else:
        print("  WARNING: Cannot read Messages database.")
        print("  Grant Full Disk Access to your terminal in:")
        print("    System Settings > Privacy & Security > Full Disk Access")

    # 9. Offer to start daemon
    print()
    start = _ask("Start the daemon now?", default="y")
    if start.lower() in ("y", "yes"):
        print("\nStarting Apple Flow daemon...\n")
        # Import and run inline to avoid circular imports at module level
        import asyncio

        from .daemon import run as run_daemon

        asyncio.run(run_daemon())
    else:
        print("\nRun the daemon later with: python -m apple_flow daemon")
        print("All set!")
