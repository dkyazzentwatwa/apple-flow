"""Interactive setup wizard and Apple resource bootstrap helpers.

Usage:
    python -m apple_flow setup
    python -m apple_flow setup --start-daemon
    python -m apple_flow setup --non-interactive-safe
"""

from __future__ import annotations

import asyncio
import secrets
import re
import sys
from pathlib import Path

from .gateway_setup import GatewayResourceStatus, ensure_gateway_resources, resolve_binary


def validate_phone(value: str) -> str | None:
    """Validate E.164 phone number format."""
    cleaned = value.strip()
    if re.fullmatch(r"\+\d{7,15}", cleaned):
        return cleaned
    return None


def validate_email(value: str) -> str | None:
    """Validate basic email format."""
    cleaned = value.strip()
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned):
        return cleaned
    return None


def validate_workspace_path(value: str) -> str | None:
    """Validate a workspace path and return the resolved path."""
    cleaned = value.strip()
    if not cleaned:
        return None
    path = Path(cleaned).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        return None
    return str(path)


def check_messages_db_access() -> tuple[bool, str]:
    """Check whether the current terminal process can read chat.db."""
    db_path = Path.home() / "Library" / "Messages" / "chat.db"
    if not db_path.exists():
        return False, f"Messages DB not found at {db_path}"
    try:
        with db_path.open("rb") as handle:
            handle.read(32)
        return True, "OK"
    except PermissionError:
        return False, "Permission denied (grant Full Disk Access to your terminal app)"
    except OSError as exc:
        return False, f"Cannot read Messages DB: {exc}"


def generate_env(
    *,
    phone: str,
    connector: str,
    connector_command: str,
    workspace: str,
    gateways: list[str],
    mail_address: str = "",
    reminders_list_name: str = "agent-task",
    reminders_archive_list_name: str = "agent-archive",
    notes_folder_name: str = "agent-task",
    notes_archive_folder_name: str = "agent-archive",
    notes_log_folder_name: str = "agent-logs",
    calendar_name: str = "agent-schedule",
    enable_notes_logging: bool = False,
    admin_api_token: str = "",
    enable_agent_office: bool = False,
    soul_file: str = "agent-office/SOUL.md",
) -> str:
    """Generate full `.env` content from `.env.example` with setup overrides."""
    env_example = _find_env_example_path()
    if not env_example.exists():
        raise FileNotFoundError(f".env.example not found at {env_example}")

    effective_token = admin_api_token.strip() or secrets.token_hex(32)
    overrides: dict[str, str] = {
        "apple_flow_allowed_senders": phone,
        "apple_flow_allowed_workspaces": workspace,
        "apple_flow_default_workspace": workspace,
        "apple_flow_connector": connector,
        "apple_flow_codex_cli_command": connector_command if connector == "codex-cli" else "codex",
        "apple_flow_claude_cli_command": connector_command if connector == "claude-cli" else "claude",
        "apple_flow_gemini_cli_command": connector_command if connector == "gemini-cli" else "gemini",
        "apple_flow_cline_command": connector_command if connector == "cline" else "cline",
        "apple_flow_only_poll_allowed_senders": "true",
        "apple_flow_require_chat_prefix": "false",
        "apple_flow_approval_ttl_minutes": "20",
        "apple_flow_max_messages_per_minute": "30",
        "apple_flow_admin_api_token": effective_token,
        "apple_flow_enable_mail_polling": "true" if "mail" in gateways else "false",
        "apple_flow_mail_allowed_senders": mail_address if "mail" in gateways else "",
        "apple_flow_mail_from_address": mail_address if "mail" in gateways else "",
        "apple_flow_enable_reminders_polling": "true" if "reminders" in gateways else "false",
        "apple_flow_reminders_list_name": reminders_list_name,
        "apple_flow_reminders_archive_list_name": reminders_archive_list_name,
        "apple_flow_reminders_owner": phone if "reminders" in gateways else "",
        "apple_flow_enable_notes_polling": "true" if "notes" in gateways else "false",
        "apple_flow_notes_folder_name": notes_folder_name,
        "apple_flow_notes_archive_folder_name": notes_archive_folder_name,
        "apple_flow_notes_owner": phone if "notes" in gateways else "",
        "apple_flow_enable_notes_logging": "true" if "notes" in gateways and enable_notes_logging else "false",
        "apple_flow_notes_log_folder_name": notes_log_folder_name,
        "apple_flow_enable_calendar_polling": "true" if "calendar" in gateways else "false",
        "apple_flow_calendar_name": calendar_name,
        "apple_flow_calendar_owner": phone if "calendar" in gateways else "",
        "apple_flow_enable_memory": "true" if enable_agent_office else "false",
        "apple_flow_soul_file": soul_file,
    }

    rendered = _render_env_from_example(env_example.read_text(encoding="utf-8"), overrides)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def _find_env_example_path() -> Path:
    """Resolve the project `.env.example` path from common entrypoints."""
    candidate = Path.cwd() / ".env.example"
    if candidate.exists():
        return candidate
    # src/apple_flow/setup_wizard.py -> repo root is two levels up from src
    return Path(__file__).resolve().parents[2] / ".env.example"


def _render_env_from_example(template: str, overrides: dict[str, str]) -> str:
    key_line_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    commented_key_line_re = re.compile(r"^\s*#\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    lines = template.splitlines()
    seen: set[str] = set()
    rendered: list[str] = []

    for line in lines:
        key_match = key_line_re.match(line)
        if key_match:
            key = key_match.group(1)
            if key in overrides:
                rendered.append(f"{key}={overrides[key]}")
                seen.add(key)
            else:
                rendered.append(line)
            continue

        commented_key_match = commented_key_line_re.match(line)
        if commented_key_match:
            key = commented_key_match.group(1)
            if key in overrides:
                rendered.append(f"{key}={overrides[key]}")
                seen.add(key)
            else:
                rendered.append(line)
            continue

        rendered.append(line)

    missing = [key for key in overrides if key not in seen]
    if missing:
        rendered.append("")
        rendered.append("# Added by setup wizard")
        for key in sorted(missing):
            rendered.append(f"{key}={overrides[key]}")

    return "\n".join(rendered)


def _ask(prompt: str, *, default: str = "", validator=None, allow_empty: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        try:
            raw = input(f"{prompt}{suffix}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled.")
            raise SystemExit(1) from None

        value = raw or default
        if not value and not allow_empty:
            print("  A value is required.")
            continue
        if validator:
            cleaned = validator(value)
            if cleaned is None:
                print("  Invalid value, please try again.")
                continue
            return cleaned
        return value


def _choose_connector() -> tuple[str, str]:
    options = [
        ("claude-cli", "Claude CLI (recommended)", "claude"),
        ("codex-cli", "Codex CLI", "codex"),
        ("gemini-cli", "Gemini CLI", "gemini"),
        ("cline", "Cline CLI", "cline"),
    ]
    print("\nChoose your AI connector:")
    for idx, (_, label, _) in enumerate(options, 1):
        print(f"  {idx}) {label}")

    while True:
        selection = _ask("Select connector number", default="1")
        if not selection.isdigit():
            print("  Please enter a number.")
            continue
        index = int(selection)
        if not (1 <= index <= len(options)):
            print("  Invalid selection.")
            continue
        connector_key, _, binary = options[index - 1]
        resolved = resolve_binary(binary)
        if not resolved:
            print(f"\nCould not find `{binary}` in PATH or common install locations.")
            print("Install/auth it first, then rerun setup.")
            raise SystemExit(1)
        return connector_key, resolved


def _choose_gateways() -> list[str]:
    gateways = ["mail", "reminders", "notes", "calendar"]
    print("\nSelect optional gateways (comma-separated numbers).")
    print("Leave blank for iMessage-only mode.")
    for idx, name in enumerate(gateways, 1):
        print(f"  {idx}) {name}")
    while True:
        raw = _ask("Gateways", default="", allow_empty=True)
        if not raw:
            return []
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        picked: list[str] = []
        valid = True
        for part in parts:
            if not part.isdigit() or not (1 <= int(part) <= len(gateways)):
                print(f"  Invalid selection: {part!r}")
                valid = False
                break
            gateway = gateways[int(part) - 1]
            if gateway not in picked:
                picked.append(gateway)
        if valid:
            return picked


def _ensure_gateway_resources(gateways: list[str]) -> list[GatewayResourceStatus]:
    return ensure_gateway_resources(
        enable_reminders="reminders" in gateways,
        enable_notes="notes" in gateways,
        enable_notes_logging="notes" in gateways,
        enable_calendar="calendar" in gateways,
        reminders_list_name="agent-task",
        reminders_archive_list_name="agent-archive",
        notes_folder_name="agent-task",
        notes_archive_folder_name="agent-archive",
        notes_log_folder_name="agent-logs",
        calendar_name="agent-schedule",
    )


def run_wizard(
    *, start_daemon: bool = False, non_interactive_safe: bool = False, script_safe: bool = False
) -> None:
    """Run setup wizard in interactive terminal mode."""
    if script_safe and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        print("Setup requires an interactive terminal in --script-safe mode.")
        print("Run this command directly in Terminal/iTerm/Codex terminal.")
        raise SystemExit(1)

    print("\n" + "=" * 56)
    print("  Apple Flow Setup Wizard")
    print("=" * 56)
    print("This will generate a .env file and configure gateway defaults.\n")

    phone = _ask("Your phone number (E.164, e.g. +15551234567)", validator=validate_phone)
    connector, connector_command = _choose_connector()
    workspace = _ask(
        "Default workspace directory (must already exist)",
        default=str(Path.home()),
        validator=validate_workspace_path,
    )
    gateways = _choose_gateways()
    mail_address = ""
    if "mail" in gateways:
        mail_address = _ask("Email address for Apple Mail", validator=validate_email)

    resource_results = _ensure_gateway_resources(gateways)
    if resource_results:
        print("\nGateway resource setup:")
        for status in resource_results:
            result = status.result
            detail = f" ({result.detail})" if result.detail else ""
            print(f"  - {status.label} '{status.name}': {result.status}{detail}")

    env_content = generate_env(
        phone=phone,
        connector=connector,
        connector_command=connector_command,
        workspace=workspace,
        gateways=gateways,
        mail_address=mail_address,
    )

    env_path = Path(".env")
    if env_path.exists():
        if non_interactive_safe:
            print("\nRefusing to overwrite existing .env in --non-interactive-safe mode.")
            print("Delete or rename .env, then rerun setup.")
            raise SystemExit(1)
        overwrite = _ask("A .env already exists. Overwrite? (y/n)", default="n")
        if overwrite.lower() not in {"y", "yes"}:
            print("Keeping existing .env. Setup finished without changes.")
            return

    env_path.write_text(env_content, encoding="utf-8")
    print(f"\nWrote {env_path.resolve()}")

    can_read_messages_db, reason = check_messages_db_access()
    if can_read_messages_db:
        print("Messages DB access check: OK")
    else:
        print(f"Messages DB access check: {reason}")
        print("Grant Full Disk Access to your terminal app in System Settings > Privacy & Security.")

    if start_daemon:
        print("\nStarting daemon...\n")
        from .daemon import run as run_daemon

        asyncio.run(run_daemon())
        return

    print("\nNext step:")
    print("  - Start now: python -m apple_flow daemon")
    print("  - Or install auto-start: ./scripts/setup_autostart.sh")
    if non_interactive_safe:
        sys.stdout.flush()
