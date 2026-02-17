# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Codex Relay is a local-first daemon that bridges iMessage, Apple Mail, Apple Reminders, Apple Notes, and Apple Calendar on macOS to Codex CLI/App Server. It polls the local Messages database and (optionally) Apple Mail, Reminders, Notes, and Calendar for inbound messages/tasks, routes allowlisted senders to Codex, enforces approval workflows for mutating operations, and replies via AppleScript. Users can iMessage, email, add Reminders, write Notes, or schedule Calendar events for Codex. By default, it uses the stateless CLI connector (`codex exec`) to avoid state corruption issues.

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# Run tests
pytest -q

# Run single test file
pytest tests/test_orchestrator.py -v

# Run single test
pytest tests/test_orchestrator.py::test_function_name -v

# Start daemon (foreground, polls iMessages)
python -m codex_relay daemon

# Start admin API only
python -m codex_relay admin

# Beginner quickstart (creates venv, runs tests, starts daemon)
./scripts/start_beginner.sh

# One-command auto-start setup (does everything!)
./scripts/setup_autostart.sh
# Creates venv, installs deps, configures service, enables auto-start at boot
# Only manual step: edit .env and grant Full Disk Access
# See docs/AUTO_START_SETUP.md for details

# Uninstall auto-start
./scripts/uninstall_autostart.sh
```

## Architecture

### Data Flow
```
iMessage DB → Ingress → Policy → Orchestrator → Codex Connector → Egress → AppleScript iMessage
                                     ↓
                                   Store (SQLite state + approvals)

Apple Mail → MailIngress → Orchestrator → Codex Connector → MailEgress → AppleScript Mail.app
  (optional, polls unread)                                    (sends reply emails)

Reminders.app → RemindersIngress → Orchestrator → Codex Connector → iMessage Egress (approvals)
  (optional, polls incomplete)         ↓                               ↓
                                     Store              RemindersEgress → annotate/complete reminder

Notes.app → NotesIngress → Orchestrator → Codex Connector → iMessage Egress (approvals)
  (optional, polls folder)        ↓                               ↓
                                Store                NotesEgress → append result to note

Calendar.app → CalendarIngress → Orchestrator → Codex Connector → iMessage Egress (approvals)
  (optional, polls due events)      ↓                               ↓
                                  Store              CalendarEgress → annotate event description

POST /task → FastAPI → Orchestrator → Codex Connector → iMessage Egress
  (Siri Shortcuts / curl bridge)
```

### Core Modules (src/codex_relay/)

| Module | Responsibility |
|--------|---------------|
| `daemon.py` | Main polling loop, graceful shutdown, signal handling |
| `orchestrator.py` | Command routing, approval gates, prompt construction |
| `ingress.py` | Reads from macOS Messages chat.db |
| `egress.py` | Sends iMessages via AppleScript, deduplicates outbound |
| `policy.py` | Sender allowlist, rate limiting |
| `store.py` | Thread-safe SQLite with connection caching and indexes |
| `config.py` | Pydantic settings with `codex_relay_` env prefix, path resolution |
| `commanding.py` | Parses command prefixes (idea:, plan:, task:, etc.) |
| `codex_cli_connector.py` | Stateless CLI connector using `codex exec` (default, avoids state corruption) |
| `codex_connector.py` | Stateful app-server connector via JSON-RPC (fallback option) |
| `main.py` | FastAPI admin endpoints |
| `protocols.py` | Protocol interfaces for type-safe component injection |
| `utils.py` | Shared utilities (normalize_sender) |
| `mail_ingress.py` | Reads unread emails from Apple Mail via AppleScript |
| `mail_egress.py` | Sends reply emails via Apple Mail AppleScript |
| `reminders_ingress.py` | Polls Apple Reminders for incomplete tasks via AppleScript |
| `reminders_egress.py` | Writes results back to reminders and marks them complete |
| `notes_ingress.py` | Polls Apple Notes folder for new notes via AppleScript |
| `notes_egress.py` | Appends Codex results back to note body |
| `calendar_ingress.py` | Polls Apple Calendar for due events via AppleScript |
| `calendar_egress.py` | Writes Codex results into event description/notes |
| `voice_memo.py` | Generates voice memos from text via macOS `say` + `afconvert` |
| `models.py` | Data models and enums (RunState, ApprovalStatus, InboundMessage) |

### Command Types

- **Non-mutating** (execute immediately): `relay:`, `idea:`, `plan:`
- **Mutating** (require approval): `task:`, `project:`
- **Control**: `approve <id>`, `deny <id>`, `status`, `clear context`
- **Dashboard**: `health` (daemon stats, uptime, session count)
- **Memory**: `history:` (recent messages), `history: <query>` (search messages)
- **Workspace routing**: `@alias` prefix on any command (e.g. `task: @web-app deploy`)

### Key Safety Invariants

- `only_poll_allowed_senders=true` filters at SQL query time
- `require_chat_prefix=true` ignores messages without `relay:` prefix
- Mutating commands always go through approval workflow
- **Approval sender verification**: only the original requester can approve/deny their requests
- Duplicate outbound suppression prevents echo loops
- Graceful shutdown with SIGINT/SIGTERM handling

## Configuration

All settings use `codex_relay_` env prefix. Key settings in `.env`:

- `codex_relay_allowed_senders` - comma-separated phone numbers
- `codex_relay_allowed_workspaces` - paths Codex may access (auto-resolved to absolute)
- `codex_relay_messages_db_path` - usually `~/Library/Messages/chat.db`
- `codex_relay_use_codex_cli` - use CLI connector instead of app-server (default: true, recommended)
- `codex_relay_codex_cli_command` - path to codex binary (default: "codex")
- `codex_relay_codex_cli_context_window` - number of recent exchanges to include as context (default: 3)
- `codex_relay_codex_app_server_cmd` - app-server command (only used if use_codex_cli=false)
- `codex_relay_codex_turn_timeout_seconds` - how long to wait for Codex responses (default: 300s/5min)
- `codex_relay_enable_mail_polling` - enable Apple Mail as additional ingress (default: false)
- `codex_relay_mail_poll_account` - Mail.app account name to poll (empty = all/inbox)
- `codex_relay_mail_poll_mailbox` - mailbox to poll (default: INBOX)
- `codex_relay_mail_from_address` - sender address for outbound replies (empty = default)
- `codex_relay_mail_allowed_senders` - comma-separated email addresses to accept
- `codex_relay_mail_max_age_days` - only process emails from last N days (default: 2)
- `codex_relay_mail_signature` - signature appended to all email replies (default: "Codex 🤖, Your 24/7 Assistant")
- `codex_relay_enable_reminders_polling` - enable Apple Reminders as task queue ingress (default: false)
- `codex_relay_reminders_list_name` - Reminders list to poll (default: "Codex Tasks")
- `codex_relay_reminders_owner` - sender identity for reminder tasks (e.g. phone number; defaults to first allowed_sender)
- `codex_relay_reminders_auto_approve` - skip approval gate for reminder tasks (default: false)
- `codex_relay_reminders_poll_interval_seconds` - poll interval for Reminders (default: 5s)
- `codex_relay_workspace_aliases` - JSON dict mapping @alias names to workspace paths (default: empty)
- `codex_relay_auto_context_messages` - number of recent messages to auto-inject as context (default: 0 = disabled)
- `codex_relay_enable_notes_polling` - enable Apple Notes as long-form task ingress (default: false)
- `codex_relay_notes_folder_name` - Notes folder to poll (default: "Codex Inbox")
- `codex_relay_notes_owner` - sender identity for note tasks (defaults to first allowed_sender)
- `codex_relay_notes_auto_approve` - skip approval gate for note tasks (default: false)
- `codex_relay_notes_poll_interval_seconds` - poll interval for Notes (default: 10s)
- `codex_relay_enable_calendar_polling` - enable Apple Calendar as scheduled task ingress (default: false)
- `codex_relay_calendar_name` - Calendar to poll (default: "Codex Schedule")
- `codex_relay_calendar_owner` - sender identity for calendar tasks (defaults to first allowed_sender)
- `codex_relay_calendar_auto_approve` - skip approval gate for calendar tasks (default: false)
- `codex_relay_calendar_poll_interval_seconds` - poll interval for Calendar (default: 30s)
- `codex_relay_calendar_lookahead_minutes` - how far ahead to look for due events (default: 5)
- `codex_relay_enable_progress_streaming` - send periodic progress updates during long tasks (default: false)
- `codex_relay_progress_update_interval_seconds` - minimum seconds between progress updates (default: 30)
- `codex_relay_enable_attachments` - enable reading inbound file attachments (default: false)
- `codex_relay_max_attachment_size_mb` - max attachment size to process (default: 10)
- `codex_relay_attachment_temp_dir` - temp directory for attachment processing (default: /tmp/codex_relay_attachments)
- `codex_relay_enable_voice_memos` - convert responses to voice memos via macOS TTS (default: false)
- `codex_relay_voice_memo_voice` - macOS TTS voice name (default: "Samantha")
- `codex_relay_voice_memo_max_chars` - max characters to convert to speech (default: 2000)
- `codex_relay_voice_memo_send_text_too` - also send text response alongside voice memo (default: true)

See `.env.example` for full list. Changes to config fields require updates to both `config.py` and `.env.example`.

## Testing

Tests use pytest-asyncio with `asyncio_mode = "auto"`. Shared test fixtures (FakeStore, FakeConnector, FakeEgress) are in `tests/conftest.py`.

```bash
# Run all tests
pytest -q

# Run with verbose output
pytest -v

# Run specific test module
pytest tests/test_ingress.py -v

# Key test files
tests/test_orchestrator.py      # Core orchestration logic
tests/test_approval_security.py # Sender verification
tests/test_store_connection.py  # Connection caching, thread safety
tests/test_egress_chunking.py   # Message chunking, fingerprinting
tests/test_utils.py             # Shared utilities
tests/test_mail_ingress.py     # Apple Mail ingress
tests/test_mail_egress.py      # Apple Mail egress
tests/test_reminders_ingress.py # Apple Reminders ingress
tests/test_reminders_egress.py  # Apple Reminders egress
tests/test_notes_ingress.py     # Apple Notes ingress
tests/test_notes_egress.py      # Apple Notes egress
tests/test_calendar_ingress.py  # Apple Calendar ingress
tests/test_calendar_egress.py   # Apple Calendar egress
tests/test_workspace_routing.py # Multi-workspace @alias routing
tests/test_health_dashboard.py  # Health dashboard command
tests/test_conversation_memory.py # History command + auto-context
tests/test_progress_streaming.py  # Progress streaming during tasks
tests/test_attachments.py       # File attachment support
tests/test_siri_shortcuts.py    # POST /task Siri Shortcuts bridge
tests/test_voice_memo.py        # Voice memo generation + orchestrator integration
```

## Security Model

- **Sender allowlist**: Only messages from configured senders are processed
- **Approval workflow**: Mutating operations (task:, project:) require explicit approval
- **Sender verification**: Approvals can only be granted/denied by the original requester
- **Workspace restrictions**: Codex can only access paths in `allowed_workspaces`

## Prerequisites

- macOS with iMessage signed in
- Full Disk Access granted to terminal app (for reading chat.db)
- `codex login` run once for Codex authentication
- For Apple Mail integration: Apple Mail configured and running on this Mac
- For Apple Reminders integration: Reminders.app on this Mac, a list named per config (default: "Codex Tasks")
- For Apple Notes integration: Notes.app on this Mac, a folder named per config (default: "Codex Inbox")
- For Apple Calendar integration: Calendar.app on this Mac, a calendar named per config (default: "Codex Schedule")
