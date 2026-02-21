# DX Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all stale Codex naming, add an interactive setup wizard, and auto-create Apple app resources so non-technical users can set up Apple Flow without editing config files or manually creating folders.

**Architecture:** New `setup_wizard.py` module with interactive prompts that generates `.env`. Daemon startup auto-creates Apple app resources via AppleScript. All doc/config references updated from Codex-era names to current defaults.

**Tech Stack:** Python 3.11+, subprocess (AppleScript), existing pydantic-settings config

---

### Task 1: Rename `.codex/` to `.apple-flow/` in config

**Files:**
- Modify: `src/apple_flow/config.py:23`

**Step 1: Run existing tests to establish baseline**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest -q 2>&1 | tail -5`
Expected: All tests pass

**Step 2: Change the default db_path**

In `src/apple_flow/config.py`, line 23, change:
```python
db_path: Path = Path.home() / ".codex" / "relay.db"
```
to:
```python
db_path: Path = Path.home() / ".apple-flow" / "relay.db"
```

**Step 3: Run tests to verify nothing breaks**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest -q 2>&1 | tail -5`
Expected: All tests still pass (tests use temp paths, not the default)

**Step 4: Commit**

```bash
git add src/apple_flow/config.py
git commit -m "fix: rename default db_path from ~/.codex/ to ~/.apple-flow/"
```

---

### Task 2: Update lock path in start_beginner.sh

**Files:**
- Modify: `scripts/start_beginner.sh:34`

**Step 1: Change the hardcoded lock path**

In `scripts/start_beginner.sh`, line 34, change:
```bash
LOCK_PATH="$HOME/.codex/relay.daemon.lock"
```
to:
```bash
LOCK_PATH="$HOME/.apple-flow/relay.daemon.lock"
```

**Step 2: Commit**

```bash
git add scripts/start_beginner.sh
git commit -m "fix: update lock path in start_beginner.sh to ~/.apple-flow/"
```

---

### Task 3: Fix all stale doc references (Codex naming + .codex/ paths)

**Files:**
- Modify: `README.md` (lines 171, 174, 177, 307, 310)
- Modify: `CLAUDE.md` (lines 427-429)
- Modify: `docs/QUICKSTART.md` (lines 332, 385, 389, 397, 400, 408, 411)
- Modify: `AGENTS.md` (lines 341-343, 418-419)
- Modify: `SECURITY.md` (line 87)
- Modify: `docs/SKILLS_AND_MCP.md` (lines 42, 94, 95, 102, 123, 124, 161)

**Step 1: Fix README.md**

Replace all occurrences:
- `"Codex Tasks"` → `"agent-task"`
- `"Codex Inbox"` → `"agent-task"`
- `"Codex Schedule"` → `"agent-schedule"`
- `apple_flow_notes_folder_name=Codex Inbox` → `apple_flow_notes_folder_name=agent-task`
- Remove the manual creation instructions — the wizard and daemon will handle this

**Step 2: Fix CLAUDE.md**

Replace the Prerequisites lines:
- `a list named per config (default: "Codex Tasks")` → `a list named per config (default: "agent-task")`
- `a folder named per config (default: "Codex Inbox")` → `a folder named per config (default: "agent-task")`
- `a calendar named per config (default: "Codex Schedule")` → `a calendar named per config (default: "agent-schedule")`

**Step 3: Fix docs/QUICKSTART.md**

Replace all Codex-era names with actual defaults:
- `Codex Tasks` → `agent-task`
- `Codex Inbox` → `agent-task`
- `Codex Schedule` → `agent-schedule`
- `~/.codex/relay.daemon.lock` → `~/.apple-flow/relay.daemon.lock`

**Step 4: Fix AGENTS.md**

Replace Codex-era defaults (lines 341-343) same as CLAUDE.md.
Remove stale skill paths referencing `/Users/cypher-server/.codex/skills/` (lines 418-419).

**Step 5: Fix SECURITY.md**

Line 87: `~/.codex/relay.db` → `~/.apple-flow/relay.db`

**Step 6: Fix docs/SKILLS_AND_MCP.md**

All `~/.codex/config.toml` references: these are Codex CLI config paths, not Apple Flow paths. Replace with a note that these paths are Codex-specific and only apply if using the Codex CLI connector. Or remove if not relevant to Apple Flow users.

**Step 7: Run tests**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest -q 2>&1 | tail -5`
Expected: All tests pass

**Step 8: Commit**

```bash
git add README.md CLAUDE.md AGENTS.md SECURITY.md docs/QUICKSTART.md docs/SKILLS_AND_MCP.md
git commit -m "docs: fix all stale Codex naming and .codex/ path references"
```

---

### Task 4: Clean up .env.example

**Files:**
- Modify: `.env.example`

**Step 1: Clean up the file**

Changes:
1. Remove `apple_flow_codex_app_server_cmd=codex app-server` (line 14, deprecated)
2. Remove `apple_flow_use_codex_cli=true` (line 18, superseded by connector field)
3. Uncomment and set `apple_flow_connector=claude-cli` as the active default (remove the second commented connector block at lines 23-25)
4. Update comments for Reminders, Notes, Calendar to use actual default names (`agent-task`, `agent-schedule`)
5. Remove stale comments that say "create a list called Codex Tasks" etc.
6. Add a comment pointing users to `python -m apple_flow setup` as the recommended way to configure

**Step 2: Run tests**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest -q 2>&1 | tail -5`
Expected: All tests pass

**Step 3: Commit**

```bash
git add .env.example
git commit -m "chore: clean up .env.example, remove deprecated options"
```

---

### Task 5: Build the setup wizard

**Files:**
- Create: `src/apple_flow/setup_wizard.py`
- Create: `tests/test_setup_wizard.py`
- Modify: `src/apple_flow/__main__.py:214` (add "setup" to mode choices)

**Step 1: Write the failing test for phone number validation**

Create `tests/test_setup_wizard.py`:
```python
"""Tests for the interactive setup wizard."""
import pytest


def test_validate_phone_valid_e164():
    from apple_flow.setup_wizard import validate_phone
    assert validate_phone("+15551234567") == "+15551234567"


def test_validate_phone_strips_whitespace():
    from apple_flow.setup_wizard import validate_phone
    assert validate_phone("  +15551234567  ") == "+15551234567"


def test_validate_phone_rejects_no_plus():
    from apple_flow.setup_wizard import validate_phone
    assert validate_phone("5551234567") is None


def test_validate_phone_rejects_too_short():
    from apple_flow.setup_wizard import validate_phone
    assert validate_phone("+1555") is None


def test_validate_phone_rejects_letters():
    from apple_flow.setup_wizard import validate_phone
    assert validate_phone("+1555abc4567") is None
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest tests/test_setup_wizard.py -v 2>&1 | tail -10`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write the setup wizard module**

Create `src/apple_flow/setup_wizard.py`:
```python
"""Interactive setup wizard for Apple Flow.

Guides non-technical users through configuration by asking simple questions
and generating a .env file. Also auto-creates Apple app resources (Reminders
lists, Notes folders, Calendar calendars) via AppleScript.

Usage:
    python -m apple_flow setup
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# ── Validation ────────────────────────────────────────────────────────────

_E164_RE = re.compile(r"^\+\d{7,15}$")


def validate_phone(value: str) -> str | None:
    """Return cleaned E.164 phone number or None if invalid."""
    cleaned = value.strip()
    if _E164_RE.match(cleaned):
        return cleaned
    return None


# ── AppleScript helpers ──────────────────────────────────────────────────

def _run_applescript(script: str) -> str:
    """Run an AppleScript and return stdout."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=10,
    )
    return result.stdout.strip()


def ensure_reminders_list(list_name: str) -> bool:
    """Create a Reminders list if it doesn't exist. Returns True if created."""
    script = f'''
    tell application "Reminders"
        try
            set existingList to list "{list_name}"
            return "exists"
        on error
            make new list with properties {{name:"{list_name}"}}
            return "created"
        end try
    end tell
    '''
    result = _run_applescript(script)
    return "created" in result


def ensure_notes_folder(folder_name: str) -> bool:
    """Create a Notes folder if it doesn't exist. Returns True if created."""
    script = f'''
    tell application "Notes"
        if not (exists folder "{folder_name}") then
            make new folder with properties {{name:"{folder_name}"}}
            return "created"
        else
            return "exists"
        end if
    end tell
    '''
    result = _run_applescript(script)
    return "created" in result


def ensure_calendar(calendar_name: str) -> bool:
    """Create a Calendar if it doesn't exist. Returns True if created."""
    script = f'''
    tell application "Calendar"
        try
            set existingCal to calendar "{calendar_name}"
            return "exists"
        on error
            make new calendar with properties {{name:"{calendar_name}"}}
            return "created"
        end try
    end tell
    '''
    result = _run_applescript(script)
    return "created" in result


def check_full_disk_access() -> bool:
    """Check if we can read the Messages database (proxy for Full Disk Access)."""
    db_path = Path.home() / "Library" / "Messages" / "chat.db"
    if not db_path.exists():
        return False
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False


# ── .env generation ──────────────────────────────────────────────────────

CONNECTOR_CHOICES = {
    "1": ("claude-cli", "Claude Code CLI"),
    "2": ("codex-cli", "Codex CLI"),
    "3": ("cline", "Cline CLI"),
}

GATEWAY_CHOICES = {
    "1": "mail",
    "2": "reminders",
    "3": "notes",
    "4": "calendar",
}


def generate_env(
    phone: str,
    connector: str,
    workspace: str,
    gateways: list[str],
    mail_address: str = "",
) -> str:
    """Generate .env file content from wizard answers."""
    lines = [
        "# Generated by: python -m apple_flow setup",
        f"apple_flow_allowed_senders={phone}",
        f"apple_flow_allowed_workspaces={workspace}",
        f"apple_flow_default_workspace={workspace}",
        f"apple_flow_connector={connector}",
        "",
        "# Polling",
        "apple_flow_poll_interval_seconds=2",
        "apple_flow_only_poll_allowed_senders=true",
        "apple_flow_require_chat_prefix=false",
        "",
    ]

    if "mail" in gateways:
        lines += [
            "# Apple Mail",
            "apple_flow_enable_mail_polling=true",
            f"apple_flow_mail_allowed_senders={mail_address}",
            "",
        ]

    if "reminders" in gateways:
        lines += [
            "# Apple Reminders",
            "apple_flow_enable_reminders_polling=true",
            "apple_flow_reminders_list_name=agent-task",
            "",
        ]

    if "notes" in gateways:
        lines += [
            "# Apple Notes",
            "apple_flow_enable_notes_polling=true",
            "apple_flow_notes_folder_name=agent-task",
            "",
        ]

    if "calendar" in gateways:
        lines += [
            "# Apple Calendar",
            "apple_flow_enable_calendar_polling=true",
            "apple_flow_calendar_name=agent-schedule",
            "",
        ]

    return "\n".join(lines) + "\n"


# ── Interactive prompts ──────────────────────────────────────────────────

def _ask(prompt: str, validate=None, default: str = "") -> str:
    """Ask a question, retry until valid."""
    while True:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default:
            raw = default
        if validate:
            result = validate(raw)
            if result is None:
                print("  Invalid input. Try again.")
                continue
            return result
        return raw


def _ask_choice(prompt: str, choices: dict[str, tuple | str], multi: bool = False) -> list[str] | str:
    """Ask user to pick from numbered choices."""
    print(f"\n{prompt}")
    for key, val in choices.items():
        label = val[1] if isinstance(val, tuple) else val
        print(f"  [{key}] {label}")
    if multi:
        print("  [a] All of the above")

    while True:
        raw = input("> ").strip().lower()
        if multi and raw == "a":
            return [v[0] if isinstance(v, tuple) else v for v in choices.values()]
        if multi:
            keys = [k.strip() for k in raw.replace(",", " ").split()]
            if all(k in choices for k in keys):
                return [choices[k][0] if isinstance(choices[k], tuple) else choices[k] for k in keys]
        elif raw in choices:
            val = choices[raw]
            return val[0] if isinstance(val, tuple) else val
        print("  Invalid choice. Try again.")


def run_wizard() -> None:
    """Run the interactive setup wizard."""
    print()
    print("=" * 50)
    print("  Welcome to Apple Flow Setup")
    print("=" * 50)
    print()

    # 1. Phone number
    phone = _ask(
        "Your phone number (E.164 format, e.g. +15551234567)",
        validate=validate_phone,
    )

    # 2. Connector
    connector = _ask_choice(
        "Which AI backend?",
        {
            "1": ("claude-cli", "Claude Code CLI (recommended)"),
            "2": ("codex-cli", "Codex CLI (OpenAI)"),
            "3": ("cline", "Cline CLI (multi-provider)"),
        },
    )

    # 3. Workspace
    default_ws = str(Path.home())
    workspace = _ask(
        "Workspace folder the AI can access",
        default=default_ws,
    )
    workspace = str(Path(workspace).expanduser().resolve())

    # 4. Gateways
    gateways = _ask_choice(
        "Which Apple apps do you want as task gateways? (pick numbers, or 'a' for all)",
        {
            "1": ("mail", "Apple Mail"),
            "2": ("reminders", "Apple Reminders"),
            "3": ("notes", "Apple Notes"),
            "4": ("calendar", "Apple Calendar"),
        },
        multi=True,
    )

    # 4b. Mail address if mail enabled
    mail_address = ""
    if "mail" in gateways:
        mail_address = _ask("Your email address (for mail gateway)")

    # 5. Auto-create Apple app resources
    print()
    if "reminders" in gateways:
        print("Creating 'agent-task' list in Reminders...", end=" ", flush=True)
        try:
            ensure_reminders_list("agent-task")
            print("done.")
        except Exception:
            print("skipped (Reminders not available).")

    if "notes" in gateways:
        print("Creating 'agent-task' folder in Notes...", end=" ", flush=True)
        try:
            ensure_notes_folder("agent-task")
            print("done.")
        except Exception:
            print("skipped (Notes not available).")

    if "calendar" in gateways:
        print("Creating 'agent-schedule' calendar...", end=" ", flush=True)
        try:
            ensure_calendar("agent-schedule")
            print("done.")
        except Exception:
            print("skipped (Calendar not available).")

    # 6. Generate .env
    env_content = generate_env(
        phone=phone,
        connector=connector,
        workspace=workspace,
        gateways=gateways,
        mail_address=mail_address,
    )

    env_path = Path.cwd() / ".env"
    if env_path.exists():
        overwrite = input(f"\n.env already exists. Overwrite? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("Keeping existing .env. You can edit it manually.")
            return
    env_path.write_text(env_content)
    print(f"\n.env written to {env_path}")

    # 7. Check Full Disk Access
    print()
    if check_full_disk_access():
        print("Full Disk Access: OK")
    else:
        print("=" * 50)
        print("  ACTION REQUIRED: Grant Full Disk Access")
        print("=" * 50)
        print()
        print("  1. Open: System Settings > Privacy & Security > Full Disk Access")
        print("  2. Click '+' and add your terminal app")
        print("  3. Restart your terminal")
        print()

    # 8. Offer to start
    print()
    start = input("Start Apple Flow now? [Y/n]: ").strip().lower()
    if start != "n":
        print("\nStarting daemon... (Ctrl+C to stop)")
        import asyncio
        from .daemon import run as run_daemon
        asyncio.run(run_daemon())
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest tests/test_setup_wizard.py -v 2>&1 | tail -10`
Expected: All 5 tests pass

**Step 5: Write tests for .env generation**

Add to `tests/test_setup_wizard.py`:
```python
def test_generate_env_basic():
    from apple_flow.setup_wizard import generate_env
    result = generate_env(
        phone="+15551234567",
        connector="claude-cli",
        workspace="/Users/test/code",
        gateways=[],
    )
    assert "apple_flow_allowed_senders=+15551234567" in result
    assert "apple_flow_connector=claude-cli" in result
    assert "apple_flow_allowed_workspaces=/Users/test/code" in result
    assert "mail" not in result.lower().split("connector")[0]  # no mail section


def test_generate_env_with_all_gateways():
    from apple_flow.setup_wizard import generate_env
    result = generate_env(
        phone="+15551234567",
        connector="codex-cli",
        workspace="/Users/test",
        gateways=["mail", "reminders", "notes", "calendar"],
        mail_address="test@example.com",
    )
    assert "apple_flow_enable_mail_polling=true" in result
    assert "apple_flow_mail_allowed_senders=test@example.com" in result
    assert "apple_flow_enable_reminders_polling=true" in result
    assert "apple_flow_enable_notes_polling=true" in result
    assert "apple_flow_enable_calendar_polling=true" in result


def test_generate_env_reminders_only():
    from apple_flow.setup_wizard import generate_env
    result = generate_env(
        phone="+15551234567",
        connector="claude-cli",
        workspace="/Users/test",
        gateways=["reminders"],
    )
    assert "apple_flow_enable_reminders_polling=true" in result
    assert "apple_flow_enable_mail_polling" not in result
    assert "apple_flow_enable_notes_polling" not in result
    assert "apple_flow_enable_calendar_polling" not in result
```

**Step 6: Run tests**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest tests/test_setup_wizard.py -v 2>&1 | tail -15`
Expected: All 8 tests pass

**Step 7: Commit**

```bash
git add src/apple_flow/setup_wizard.py tests/test_setup_wizard.py
git commit -m "feat: add interactive setup wizard with phone validation and .env generation"
```

---

### Task 6: Wire up the setup subcommand in __main__.py

**Files:**
- Modify: `src/apple_flow/__main__.py:214,248-249`

**Step 1: Add "setup" to the mode choices**

In `__main__.py`, line 214, change:
```python
parser.add_argument("mode", choices=["daemon", "admin", "tools", "version"], nargs="?", default="daemon")
```
to:
```python
parser.add_argument("mode", choices=["daemon", "admin", "tools", "setup", "version"], nargs="?", default="daemon")
```

**Step 2: Add the setup handler before the daemon block**

After line 241 (the version return), add:
```python
    if args.mode == "setup":
        from .setup_wizard import run_wizard
        run_wizard()
        return
```

**Step 3: Run all tests**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest -q 2>&1 | tail -5`
Expected: All tests pass

**Step 4: Commit**

```bash
git add src/apple_flow/__main__.py
git commit -m "feat: wire up 'python -m apple_flow setup' wizard subcommand"
```

---

### Task 7: Auto-create Apple app resources at daemon startup

**Files:**
- Modify: `src/apple_flow/daemon.py` (in `RelayDaemon.__init__` or a new method)

**Step 1: Add ensure methods to daemon startup**

In `daemon.py`, after the connector setup in `RelayDaemon.__init__`, add a call to a new method `_ensure_apple_resources()` that:
- If `enable_reminders_polling` is True, calls `ensure_reminders_list(settings.reminders_list_name)`
- If `enable_notes_polling` is True, calls `ensure_notes_folder(settings.notes_folder_name)`
- If `enable_calendar_polling` is True, calls `ensure_calendar(settings.calendar_name)`

Import from `setup_wizard`:
```python
from .setup_wizard import ensure_reminders_list, ensure_notes_folder, ensure_calendar
```

Each call is wrapped in try/except so failures don't crash the daemon — just log a warning.

**Step 2: Run all tests**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest -q 2>&1 | tail -5`
Expected: All tests pass

**Step 3: Commit**

```bash
git add src/apple_flow/daemon.py
git commit -m "feat: auto-create Apple app resources at daemon startup"
```

---

### Task 8: Update setup scripts to invoke wizard

**Files:**
- Modify: `scripts/setup_autostart.sh:50-81`
- Modify: `scripts/start_beginner.sh:43-61`

**Step 1: Update setup_autostart.sh**

In the `.env` creation block (lines 50-81), replace the "edit .env manually" flow with:
```bash
if [ ! -f "$ENV_FILE" ]; then
    echo "No .env found. Running setup wizard..."
    "$VENV_DIR/bin/python" -m apple_flow setup
fi
```

Keep the existing fallback for when `.env` already exists.

**Step 2: Update start_beginner.sh**

Same pattern: if no `.env` exists, run the wizard instead of copying .env.example and telling the user to edit it.

**Step 3: Commit**

```bash
git add scripts/setup_autostart.sh scripts/start_beginner.sh
git commit -m "feat: setup scripts invoke wizard instead of manual .env editing"
```

---

### Task 9: Final verification

**Step 1: Run full test suite**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && .venv/bin/pytest -q`
Expected: All tests pass (487+ existing + 8 new)

**Step 2: Verify no remaining stale references**

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && grep -r "Codex Tasks\|Codex Inbox\|Codex Schedule" --include="*.md" --include="*.py" --include="*.sh" --include="*.env*" | grep -v "plans/" | grep -v ".git/"`
Expected: No results (plans/ excluded since the design doc mentions them as the problem statement)

Run: `cd /Users/tiffanykyazze/Documents/GitHub/apple-flow && grep -r '\.codex/' --include="*.py" --include="*.sh" --include="*.md" | grep -v "plans/" | grep -v ".git/" | grep -v "SKILLS_AND_MCP"`
Expected: No results

**Step 3: Commit everything and verify clean state**

```bash
git status
git log --oneline -10
```
