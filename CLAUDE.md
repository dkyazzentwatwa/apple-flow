# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Codex Relay is a local-first daemon that bridges iMessage, Apple Mail, Apple Reminders, Apple Notes, and Apple Calendar on macOS to Codex CLI/App Server. It polls the local Messages database and (optionally) Apple Mail, Reminders, Notes, and Calendar for inbound messages/tasks, routes allowlisted senders to Codex, enforces approval workflows for mutating operations, and replies via AppleScript. Users can iMessage, email, add Reminders, write Notes, or schedule Calendar events for Codex. By default, it uses the stateless CLI connector (`codex exec`) to avoid state corruption issues.

**Version:** 0.1.0 | **Python:** ≥3.11 | **Package name:** `codex-relay`

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
| `__main__.py` | CLI entry point (`python -m codex_relay`), daemon lock management |
| `daemon.py` | Main polling loop, graceful shutdown, signal handling, connector selection |
| `orchestrator.py` | Command routing, approval gates, prompt construction, attachment/voice memo handling |
| `commanding.py` | Parses command prefixes (idea:, plan:, task:, @alias extraction, CommandKind enum) |
| `ingress.py` | Reads from macOS Messages chat.db (read-only SQLite, attachment extraction) |
| `egress.py` | Sends iMessages via AppleScript, deduplicates outbound messages |
| `policy.py` | Sender allowlist, rate limiting enforcement |
| `store.py` | Thread-safe SQLite with connection caching and indexes |
| `config.py` | Pydantic settings with `codex_relay_` env prefix, path resolution |
| `codex_cli_connector.py` | Stateless CLI connector using `codex exec` (default, avoids state corruption) |
| `codex_connector.py` | Stateful app-server connector via JSON-RPC (fallback option) |
| `main.py` | FastAPI admin endpoints (/sessions, /approvals, /events, POST /task) |
| `admin_client.py` | Admin API client library (programmatic access to admin endpoints) |
| `protocols.py` | Protocol interfaces for type-safe component injection (StoreProtocol, ConnectorProtocol, EgressProtocol) |
| `models.py` | Data models and enums (RunState, ApprovalStatus, CommandKind, InboundMessage, ApprovalRequest) |
| `utils.py` | Shared utilities (normalize_sender) |
| `mail_ingress.py` | Reads unread emails from Apple Mail via AppleScript |
| `mail_egress.py` | Sends threaded reply emails via Apple Mail AppleScript with signatures |
| `reminders_ingress.py` | Polls Apple Reminders for incomplete tasks via AppleScript |
| `reminders_egress.py` | Writes results back to reminders and marks them complete |
| `notes_ingress.py` | Polls Apple Notes folder for new notes via AppleScript |
| `notes_egress.py` | Appends Codex results back to note body |
| `calendar_ingress.py` | Polls Apple Calendar for due events via AppleScript |
| `calendar_egress.py` | Writes Codex results into event description/notes |
| `voice_memo.py` | Generates voice memos from text via macOS `say` + `afconvert`, handles cleanup |

### Command Types

- **Non-mutating** (execute immediately): `relay:`, `idea:`, `plan:`
- **Mutating** (require approval): `task:`, `project:`
- **Control**: `approve <id>`, `deny <id>`, `status`, `clear context`
- **Dashboard**: `health:` (daemon stats, uptime, session count)
- **Memory**: `history:` (recent messages), `history: <query>` (search messages)
- **Workspace routing**: `@alias` prefix on any command (e.g. `task: @web-app deploy`)

### Key Safety Invariants

- `only_poll_allowed_senders=true` filters at SQL query time
- `require_chat_prefix=true` ignores messages without `relay:` prefix
- Mutating commands always go through approval workflow
- **Approval sender verification**: only the original requester can approve/deny their requests
- Duplicate outbound suppression prevents echo loops
- Graceful shutdown with SIGINT/SIGTERM handling
- iMessage DB opened in read-only mode (`PRAGMA query_only`, URI read-only)
- Daemon lock file prevents multiple concurrent instances
- Rate limiting enforced per sender (`max_messages_per_minute`)

## Data Models

### Enums (models.py)

```python
class RunState(str, Enum):
    RECEIVED, PLANNING, AWAITING_APPROVAL, EXECUTING,
    VERIFYING, COMPLETED, FAILED, DENIED

class ApprovalStatus(str, Enum):
    PENDING, APPROVED, DENIED, EXPIRED

class CommandKind(str, Enum):
    CHAT, IDEA, PLAN, TASK, PROJECT, CLEAR_CONTEXT,
    APPROVE, DENY, STATUS, HEALTH, HISTORY
```

### Dataclasses (models.py)

```python
@dataclass
class InboundMessage:
    id, sender, text, received_at, is_from_me, context

@dataclass
class ApprovalRequest:
    request_id, run_id, summary, command_preview, expires_at, status
```

### SQLite Tables (store.py)

| Table | Purpose |
|-------|---------|
| `sessions` | Active sender threads |
| `messages` | Processed messages |
| `runs` | Task/project execution records |
| `approvals` | Pending approval requests |
| `events` | Audit log |
| `kv_state` | Key-value state storage |

## Configuration

All settings use `codex_relay_` env prefix. Key settings in `.env`:

### Core Settings

- `codex_relay_allowed_senders` - comma-separated phone numbers (E.164 format)
- `codex_relay_allowed_workspaces` - paths Codex may access (auto-resolved to absolute)
- `codex_relay_default_workspace` - default working directory for Codex
- `codex_relay_messages_db_path` - usually `~/Library/Messages/chat.db`

### Safety Settings

- `codex_relay_only_poll_allowed_senders` - filter at SQL query time (default: true)
- `codex_relay_require_chat_prefix` - require `relay:` prefix on messages (default: true)
- `codex_relay_chat_prefix` - custom prefix string (default: "relay:")
- `codex_relay_approval_ttl_minutes` - how long approvals remain valid (default: 20)
- `codex_relay_max_messages_per_minute` - rate limit per sender (default: 30)

### Connector Settings

- `codex_relay_use_codex_cli` - use CLI connector instead of app-server (default: true, recommended)
- `codex_relay_codex_cli_command` - path to codex binary (default: "codex")
- `codex_relay_codex_cli_context_window` - number of recent exchanges to include as context (default: 3)
- `codex_relay_codex_app_server_cmd` - app-server command (only used if use_codex_cli=false)
- `codex_relay_codex_turn_timeout_seconds` - how long to wait for Codex responses (default: 300s/5min)

### Apple Mail Integration

- `codex_relay_enable_mail_polling` - enable Apple Mail as additional ingress (default: false)
- `codex_relay_mail_poll_account` - Mail.app account name to poll (empty = all/inbox)
- `codex_relay_mail_poll_mailbox` - mailbox to poll (default: INBOX)
- `codex_relay_mail_from_address` - sender address for outbound replies (empty = default)
- `codex_relay_mail_allowed_senders` - comma-separated email addresses to accept
- `codex_relay_mail_max_age_days` - only process emails from last N days (default: 2)
- `codex_relay_mail_signature` - signature appended to all email replies (default: "Codex 🤖, Your 24/7 Assistant")

### Apple Reminders Integration

- `codex_relay_enable_reminders_polling` - enable Apple Reminders as task queue ingress (default: false)
- `codex_relay_reminders_list_name` - Reminders list to poll (default: "Codex Tasks")
- `codex_relay_reminders_owner` - sender identity for reminder tasks (e.g. phone number; defaults to first allowed_sender)
- `codex_relay_reminders_auto_approve` - skip approval gate for reminder tasks (default: false)
- `codex_relay_reminders_poll_interval_seconds` - poll interval for Reminders (default: 5s)

### Apple Notes Integration

- `codex_relay_enable_notes_polling` - enable Apple Notes as long-form task ingress (default: false)
- `codex_relay_notes_folder_name` - Notes folder to poll (default: "Codex Inbox")
- `codex_relay_notes_owner` - sender identity for note tasks (defaults to first allowed_sender)
- `codex_relay_notes_auto_approve` - skip approval gate for note tasks (default: false)
- `codex_relay_notes_poll_interval_seconds` - poll interval for Notes (default: 10s)

### Apple Calendar Integration

- `codex_relay_enable_calendar_polling` - enable Apple Calendar as scheduled task ingress (default: false)
- `codex_relay_calendar_name` - Calendar to poll (default: "Codex Schedule")
- `codex_relay_calendar_owner` - sender identity for calendar tasks (defaults to first allowed_sender)
- `codex_relay_calendar_auto_approve` - skip approval gate for calendar tasks (default: false)
- `codex_relay_calendar_poll_interval_seconds` - poll interval for Calendar (default: 30s)
- `codex_relay_calendar_lookahead_minutes` - how far ahead to look for due events (default: 5)

### Advanced Features

- `codex_relay_workspace_aliases` - JSON dict mapping @alias names to workspace paths (default: empty)
- `codex_relay_auto_context_messages` - number of recent messages to auto-inject as context (default: 0 = disabled)
- `codex_relay_enable_progress_streaming` - send periodic progress updates during long tasks (default: false)
- `codex_relay_progress_update_interval_seconds` - minimum seconds between progress updates (default: 30)
- `codex_relay_enable_attachments` - enable reading inbound file attachments (default: false)
- `codex_relay_max_attachment_size_mb` - max attachment size to process (default: 10)
- `codex_relay_attachment_temp_dir` - temp directory for attachment processing (default: /tmp/codex_relay_attachments)
- `codex_relay_enable_voice_memos` - convert responses to voice memos via macOS TTS (default: false)
- `codex_relay_voice_memo_voice` - macOS TTS voice name (default: "Samantha")
- `codex_relay_voice_memo_max_chars` - max characters to convert to speech (default: 2000)
- `codex_relay_voice_memo_send_text_too` - also send text response alongside voice memo (default: true)

See `.env.example` for full list. **When adding a new config field:** update both `config.py` and `.env.example`, add docs to `README.md`, and ensure a sensible default.

## Admin API

The admin API runs on port 8787 by default (`python -m codex_relay admin`).

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/sessions` | GET | List active sender threads |
| `/approvals/pending` | GET | List pending approval requests |
| `/events` | GET | Audit log |
| `/task` | POST | Submit a task programmatically (Siri Shortcuts / curl) |

## Testing

Tests use pytest-asyncio with `asyncio_mode = "auto"`. Shared test fixtures (FakeStore, FakeConnector, FakeEgress) are in `tests/conftest.py`.

```bash
# Run all tests
pytest -q

# Run with verbose output
pytest -v

# Run specific test module
pytest tests/test_ingress.py -v

# Run single test function
pytest tests/test_orchestrator.py::test_function_name -v
```

### Test Files

```
# Core logic
tests/conftest.py               # Shared fixtures: FakeConnector, FakeEgress, FakeStore
tests/test_orchestrator.py      # Core orchestration logic, command routing
tests/test_approval_security.py # Sender verification for approve/deny
tests/test_command_parser.py    # Command parsing, @alias extraction
tests/test_store.py             # SQLite CRUD operations
tests/test_store_connection.py  # Connection caching, thread safety
tests/test_egress.py            # Basic egress functionality
tests/test_egress_chunking.py   # Message chunking, fingerprinting for dedup
tests/test_policy.py            # Sender allowlist, rate limiting
tests/test_config.py            # Configuration loading from .env
tests/test_config_env.py        # Environment variable parsing
tests/test_utils.py             # Shared utilities

# iMessage integration
tests/test_ingress.py           # Basic iMessage ingress
tests/test_ingress_filter.py    # Sender filtering
tests/test_ingress_strict.py    # Chat prefix validation

# Apple app integrations
tests/test_mail_ingress.py      # Apple Mail ingress
tests/test_mail_egress.py       # Apple Mail egress
tests/test_reminders_ingress.py # Apple Reminders ingress
tests/test_reminders_egress.py  # Apple Reminders egress (mark complete, annotate)
tests/test_notes_ingress.py     # Apple Notes ingress
tests/test_notes_egress.py      # Apple Notes egress (append results)
tests/test_calendar_ingress.py  # Apple Calendar ingress
tests/test_calendar_egress.py   # Apple Calendar egress (write results to event)

# Features
tests/test_workspace_routing.py   # Multi-workspace @alias routing
tests/test_health_dashboard.py    # Health command, daemon statistics
tests/test_conversation_memory.py # History command + auto-context injection
tests/test_siri_shortcuts.py      # POST /task admin API endpoint
tests/test_progress_streaming.py  # Incremental progress updates
tests/test_attachments.py         # File attachment support
tests/test_voice_memo.py          # Voice memo generation + orchestrator integration
tests/test_cli_connector.py       # Stateless CLI connector (codex exec)
tests/test_admin_api.py           # FastAPI admin endpoints
```

## Security Model

- **Sender allowlist**: Only messages from configured senders are processed
- **Approval workflow**: Mutating operations (task:, project:) require explicit approval
- **Sender verification**: Approvals can only be granted/denied by the original requester
- **Workspace restrictions**: Codex can only access paths in `allowed_workspaces`
- **Read-only iMessage DB**: Opened with `PRAGMA query_only` and URI read-only mode
- **Rate limiting**: Configurable max messages per minute per sender
- **Daemon lock**: Prevents multiple concurrent instances from running

## Prerequisites

- macOS with iMessage signed in
- Full Disk Access granted to terminal app (for reading chat.db)
- `codex login` run once for Codex authentication
- For Apple Mail integration: Apple Mail configured and running on this Mac
- For Apple Reminders integration: Reminders.app on this Mac, a list named per config (default: "Codex Tasks")
- For Apple Notes integration: Notes.app on this Mac, a folder named per config (default: "Codex Inbox")
- For Apple Calendar integration: Calendar.app on this Mac, a calendar named per config (default: "Codex Schedule")

## Service Management (launchd)

```bash
# Start/stop service
launchctl start com.codex.relay
launchctl stop com.codex.relay

# Check service status
launchctl list | grep codex.relay

# View logs
tail -f logs/codex-relay.log
tail -f logs/codex-relay.err.log
```

## Conventions for AI Assistants

### After any behavior change
Always run `pytest -q` to verify tests pass before considering the task complete.

### Adding a new Apple app integration
Follow the established pattern: create `<app>_ingress.py` and `<app>_egress.py`, add config fields to `config.py` and `.env.example`, wire up in `daemon.py`, and add test files `tests/test_<app>_ingress.py` and `tests/test_<app>_egress.py`.

### Adding a new config field
1. Add the field with a default to `src/codex_relay/config.py`
2. Add the commented example to `.env.example`
3. Document it in `README.md`
4. Update `CLAUDE.md` (this file) if it's a key setting

### Adding a new command type
1. Add the variant to `CommandKind` enum in `models.py`
2. Parse it in `commanding.py`
3. Handle it in `orchestrator.py`
4. Add tests to `tests/test_command_parser.py` and `tests/test_orchestrator.py`

### Connector selection
- Default: `codex_cli_connector.py` (stateless, `codex exec`, recommended)
- Fallback: `codex_connector.py` (stateful JSON-RPC app-server)
- Selection controlled by `codex_relay_use_codex_cli` config flag

### Key patterns
- All async I/O uses `asyncio`; test with `pytest-asyncio` (`asyncio_mode = "auto"`)
- Phone number normalization via `utils.normalize_sender()` for consistent sender IDs
- AppleScript calls are the mechanism for all Apple app interactions (Mail, Reminders, Notes, Calendar)
- Store operations are thread-safe via connection caching in `store.py`
- Protocol interfaces in `protocols.py` enable fake implementations for tests

## Project Statistics

| Metric | Value |
|--------|-------|
| Source modules | 24 |
| Test files | 31 |
| Config options | 40+ |
| Python requirement | ≥3.11 |
| Core dependencies | fastapi, uvicorn, pydantic, pydantic-settings, httpx |
| Dev dependencies | pytest, pytest-asyncio, httpx |
