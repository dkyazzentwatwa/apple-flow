from __future__ import annotations

import argparse
import asyncio
import atexit
import fcntl
import importlib.metadata
import json
import sys
from pathlib import Path

import uvicorn

from .apple_tools import (
    TOOLS_CONTEXT,
    calendar_create,
    calendar_list_calendars,
    calendar_list_events,
    calendar_search,
    mail_get_content,
    mail_list_unread,
    mail_search,
    mail_send,
    messages_list_recent_chats,
    messages_search,
    notes_append,
    notes_create,
    notes_get_content,
    notes_list,
    notes_list_folders,
    notes_search,
    reminders_complete,
    reminders_create,
    reminders_list,
    reminders_list_lists,
    reminders_search,
)
from .cli_control import run_cli_control
from .config import RelaySettings
from .daemon import run as run_daemon
from .setup_wizard import run_wizard

_LOCK_FILE = None


def _acquire_daemon_lock() -> tuple[int, Path]:
    settings = RelaySettings()
    lock_path = Path(settings.db_path).with_suffix(".daemon.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = lock_path.open("w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(
            f"Another Apple Flow daemon appears to be running (lock: {lock_path})."
        ) from exc
    lock_fd.write(str(Path.cwd()))
    lock_fd.flush()
    global _LOCK_FILE
    _LOCK_FILE = lock_fd
    atexit.register(lock_fd.close)
    return lock_fd.fileno(), lock_path


# ---------------------------------------------------------------------------
# Tools subcommand dispatcher
# ---------------------------------------------------------------------------

def _run_tools_subcommand(args: argparse.Namespace) -> None:
    """Dispatch to apple_tools functions based on CLI args."""
    tool_args: list[str] = args.tool_args or []

    # apple-flow tools --list  →  print TOOLS_CONTEXT
    if not tool_args or args.list_tools:
        print(TOOLS_CONTEXT)
        return

    command = tool_args[0]
    positional = tool_args[1:]  # positional args after command name

    as_text: bool = args.text
    limit: int = args.limit

    def _output(result) -> None:
        if isinstance(result, str):
            print(result)
        else:
            print(json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False))

    # ── Notes ──────────────────────────────────────────────────────────────
    if command == "notes_list_folders":
        _output(notes_list_folders())

    elif command == "notes_list":
        _output(notes_list(folder=args.folder or "", limit=limit, as_text=as_text))

    elif command == "notes_search":
        if not positional:
            print("Usage: apple-flow tools notes_search <query> [--folder X] [--limit N]", file=sys.stderr)
            raise SystemExit(1)
        _output(notes_search(positional[0], folder=args.folder or "", limit=limit, as_text=as_text))

    elif command == "notes_get_content":
        if not positional:
            print("Usage: apple-flow tools notes_get_content <title> [--folder X]", file=sys.stderr)
            raise SystemExit(1)
        _output(notes_get_content(positional[0], folder=args.folder or ""))

    elif command == "notes_create":
        if len(positional) < 2:
            print("Usage: apple-flow tools notes_create <title> <body> [--folder X]", file=sys.stderr)
            raise SystemExit(1)
        _output(notes_create(positional[0], positional[1], folder=args.folder or ""))

    elif command == "notes_append":
        if len(positional) < 2:
            print("Usage: apple-flow tools notes_append <title> <text> [--folder X]", file=sys.stderr)
            raise SystemExit(1)
        _output(notes_append(positional[0], positional[1], folder=args.folder or ""))

    # ── Mail ───────────────────────────────────────────────────────────────
    elif command == "mail_list_unread":
        _output(mail_list_unread(account=args.account or "", mailbox=args.mailbox or "INBOX", limit=limit, as_text=as_text))

    elif command == "mail_search":
        if not positional:
            print("Usage: apple-flow tools mail_search <query> [--days N] [--limit N]", file=sys.stderr)
            raise SystemExit(1)
        _output(mail_search(positional[0], account=args.account or "", mailbox=args.mailbox or "INBOX", limit=limit, max_age_days=args.days or 30, as_text=as_text))

    elif command == "mail_get_content":
        if not positional:
            print("Usage: apple-flow tools mail_get_content <message_id>", file=sys.stderr)
            raise SystemExit(1)
        _output(mail_get_content(positional[0], account=args.account or "", mailbox=args.mailbox or "INBOX"))

    elif command == "mail_send":
        if len(positional) < 3:
            print("Usage: apple-flow tools mail_send <to> <subject> <body>", file=sys.stderr)
            raise SystemExit(1)
        _output(mail_send(positional[0], positional[1], positional[2], account=args.account or ""))

    # ── Reminders ──────────────────────────────────────────────────────────
    elif command == "reminders_list_lists":
        _output(reminders_list_lists())

    elif command == "reminders_list":
        _output(reminders_list(list_name=args.list or "", filter=args.filter or "incomplete", limit=limit, as_text=as_text))

    elif command == "reminders_search":
        if not positional:
            print("Usage: apple-flow tools reminders_search <query> [--list X] [--limit N]", file=sys.stderr)
            raise SystemExit(1)
        _output(reminders_search(positional[0], list_name=args.list or "", limit=limit, as_text=as_text))

    elif command == "reminders_create":
        if not positional:
            print("Usage: apple-flow tools reminders_create <name> [--list X] [--due YYYY-MM-DD]", file=sys.stderr)
            raise SystemExit(1)
        _output(reminders_create(positional[0], list_name=args.list or "Reminders", due_date=args.due or ""))

    elif command == "reminders_complete":
        if not positional or not args.list:
            print("Usage: apple-flow tools reminders_complete <id> --list <ListName>", file=sys.stderr)
            raise SystemExit(1)
        _output(reminders_complete(positional[0], list_name=args.list))

    # ── Calendar ───────────────────────────────────────────────────────────
    elif command == "calendar_list_calendars":
        _output(calendar_list_calendars())

    elif command == "calendar_list_events":
        cal = args.cal or args.calendar_name or ""
        _output(calendar_list_events(calendar=cal, days_ahead=args.days or 7, limit=limit, as_text=as_text))

    elif command == "calendar_search":
        if not positional:
            print("Usage: apple-flow tools calendar_search <query> [--cal X] [--limit N]", file=sys.stderr)
            raise SystemExit(1)
        cal = args.cal or args.calendar_name or ""
        _output(calendar_search(positional[0], calendar=cal, limit=limit, as_text=as_text))

    elif command == "calendar_create":
        if len(positional) < 2:
            print("Usage: apple-flow tools calendar_create <title> <start_date> [--end X] [--cal X]", file=sys.stderr)
            raise SystemExit(1)
        cal = args.cal or args.calendar_name or ""
        _output(calendar_create(positional[0], positional[1], end_date=args.end or "", calendar=cal))

    # ── Messages ───────────────────────────────────────────────────────────
    elif command == "messages_list_recent_chats":
        _output(messages_list_recent_chats(limit=limit, as_text=as_text))

    elif command == "messages_search":
        if not positional:
            print("Usage: apple-flow tools messages_search <query> [--limit N]", file=sys.stderr)
            raise SystemExit(1)
        _output(messages_search(positional[0], limit=limit, as_text=as_text))

    else:
        print(f"Unknown tool: {command!r}\n", file=sys.stderr)
        print(TOOLS_CONTEXT, file=sys.stderr)
        raise SystemExit(1)


def _get_version() -> str:
    """Get the version from package metadata."""
    try:
        return importlib.metadata.version("apple-flow")
    except importlib.metadata.PackageNotFoundError:
        return "0.2.1 (dev)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Apple Flow runtime")
    parser.add_argument(
        "mode",
        choices=["daemon", "admin", "tools", "setup", "wizard", "config", "service", "version"],
        nargs="?",
        default="daemon",
    )
    parser.add_argument("--version", "-V", action="store_true", help="Show version and exit")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--start-daemon",
        dest="start_daemon",
        action="store_true",
        help="When used with `setup`, start daemon after generating config.",
    )
    parser.add_argument(
        "--non-interactive-safe",
        dest="non_interactive_safe",
        action="store_true",
        help="When used with `setup`, never overwrite existing .env.",
    )
    parser.add_argument(
        "--script-safe",
        dest="script_safe",
        action="store_true",
        help="When used with `setup`, fail fast if no interactive terminal is attached.",
    )

    # Tools-specific flags (only used when mode=tools)
    parser.add_argument("tool_args", nargs="*", help="Tool name followed by its positional arguments")
    parser.add_argument("--list", dest="list", metavar="LIST", help="Reminders list name")
    parser.add_argument("--folder", dest="folder", metavar="FOLDER", help="Notes folder name")
    parser.add_argument("--cal", dest="cal", metavar="CALENDAR", help="Calendar name")
    parser.add_argument("--account", dest="account", metavar="ACCOUNT", help="Mail account name")
    parser.add_argument("--mailbox", dest="mailbox", metavar="MAILBOX", help="Mail mailbox name")
    parser.add_argument("--limit", dest="limit", type=int, default=20, metavar="N", help="Maximum results")
    parser.add_argument("--days", dest="days", type=int, default=None, metavar="N", help="Day range")
    parser.add_argument("--filter", dest="filter", metavar="FILTER", help="incomplete|complete|all")
    parser.add_argument("--due", dest="due", metavar="DATE", help="Due date (YYYY-MM-DD)")
    parser.add_argument("--end", dest="end", metavar="DATETIME", help="End datetime for calendar events")
    parser.add_argument("--text", dest="text", action="store_true", help="Output human-readable text")
    parser.add_argument("--pretty", dest="pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--list-tools", dest="list_tools", action="store_true", help="Print available tools")
    # Internal alias used by calendar_list_events/calendar_search
    parser.add_argument("--calendar", dest="calendar_name", metavar="CALENDAR", help=argparse.SUPPRESS)

    # Wizard/config/service machine-mode options
    parser.add_argument("--env-file", dest="env_file", default=".env", help="Path to .env file")
    parser.add_argument("--set", dest="set_values", action="append", help="Set key=value pairs in .env")
    parser.add_argument("--key", dest="keys", action="append", help="Read specific key(s) from .env")
    parser.add_argument("--stream", dest="stream_name", choices=["stderr", "stdout"], default="stderr")
    parser.add_argument("--lines", dest="lines", type=int, default=200)

    parser.add_argument("--phone", dest="phone", default="")
    parser.add_argument("--connector", dest="connector", default="")
    parser.add_argument("--connector-command", dest="connector_command", default="")
    parser.add_argument("--workspace", dest="workspace", default="")
    parser.add_argument("--gateways", dest="gateways", default="")
    parser.add_argument("--mail-address", dest="mail_address", default="")
    parser.add_argument("--admin-api-token", dest="admin_api_token", default="")
    parser.add_argument("--enable-agent-office", dest="enable_agent_office", action="store_true")
    parser.add_argument("--soul-file", dest="soul_file", default="agent-office/SOUL.md")

    parser.add_argument("--enable-reminders", dest="enable_reminders", action="store_true")
    parser.add_argument("--enable-notes", dest="enable_notes", action="store_true")
    parser.add_argument("--enable-notes-logging", dest="enable_notes_logging", action="store_true")
    parser.add_argument("--enable-calendar", dest="enable_calendar", action="store_true")

    parser.add_argument("--reminders-list-name", dest="reminders_list_name", default="agent-task")
    parser.add_argument(
        "--reminders-archive-list-name",
        dest="reminders_archive_list_name",
        default="agent-archive",
    )
    parser.add_argument("--notes-folder-name", dest="notes_folder_name", default="agent-task")
    parser.add_argument("--notes-archive-folder-name", dest="notes_archive_folder_name", default="agent-archive")
    parser.add_argument("--notes-log-folder-name", dest="notes_log_folder_name", default="agent-logs")
    parser.add_argument("--calendar-name", dest="calendar_name_override", default="agent-schedule")

    args = parser.parse_args()

    # Handle --version flag or version mode
    if args.version or args.mode == "version":
        print(f"apple-flow {_get_version()}")
        return

    if args.mode == "daemon":
        try:
            _acquire_daemon_lock()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        asyncio.run(run_daemon())
        return

    if args.mode == "tools":
        _run_tools_subcommand(args)
        return

    if args.mode == "setup":
        run_wizard(
            start_daemon=args.start_daemon,
            non_interactive_safe=args.non_interactive_safe,
            script_safe=args.script_safe,
        )
        return

    if args.mode in {"wizard", "config", "service"}:
        raise SystemExit(run_cli_control(args.mode, args))

    settings = RelaySettings()
    uvicorn.run("apple_flow.main:app", host=settings.admin_host, port=settings.admin_port, reload=False)


if __name__ == "__main__":
    main()
