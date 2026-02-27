# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Apple Flow is a local-first daemon that bridges iMessage, Apple Mail, Apple Reminders, Apple Notes, and Apple Calendar on macOS to AI CLIs (Codex, Claude, Gemini, Cline, or app-server fallback). It polls the local Messages database and (optionally) Apple Mail, Reminders, Notes, and Calendar for inbound messages/tasks, routes allowlisted senders to the configured connector, enforces approval workflows for mutating operations, and replies via AppleScript. By default, it uses a stateless CLI connector (`codex exec`) to avoid state corruption issues.

The project also ships an optional **Autonomous Companion Layer**: a proactive loop (`companion.py`) that watches for stale approvals, upcoming calendar events, overdue reminders, and office inbox items, synthesizes observations via AI, and sends proactive iMessages. Companion state is anchored in `agent-office/` — a structured workspace directory that holds the companion's identity (`SOUL.md`), durable memory (`MEMORY.md`), topic memory files, daily notes, project briefs, and automation playbooks.

**Version:** 0.2.0 | **Python:** ≥3.11 | **Package name:** `apple-flow`

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
python -m apple_flow daemon

# Start admin API only
python -m apple_flow admin

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

### Direct Notion API Helper (No MCP)

Use `scripts/notion_direct.py` when MCP access is unavailable or you need direct Notion API calls.

```bash
# Requires NOTION_API_KEY in environment (or .env loaded into shell)
./scripts/notion_direct.py list-dbs --query "Lead Gen"
./scripts/notion_direct.py fetch <page_or_database_id>
./scripts/notion_direct.py query-db <database_id> --page-size 10
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

CompanionLoop → (stale approvals, calendar, reminders, office inbox) → AI synthesis → iMessage Egress
  (optional, proactive; respects quiet hours + rate limit)      ↓
                                                       FollowUpScheduler (scheduled_actions table)

AmbientScanner → Notes/Calendar/Mail → FileMemory (agent-office/60_memory/)
  (optional, passive context enrichment every 15 min; never sends messages)
```

### Agent Office Directory (agent-office/)

The companion's workspace, checked into the repo as a scaffold. Personal content is gitignored.

```
agent-office/
  SOUL.md              # companion identity/personality — injected into claude-cli system prompt
  MEMORY.md            # durable memory — injected into every AI prompt (when enable_memory=true)
  SCAFFOLD.md          # describes the directory structure (tracked by git)
  setup.sh             # idempotent bootstrap script — run once after cloning
  60_memory/           # topic memory files (one .md per topic; written by AmbientScanner)
  00_inbox/inbox.md    # append-only capture
  10_daily/            # daily notes (YYYY-MM-DD.md), written by companion daily digest
  20_projects/         # active project briefs
  80_automation/       # routines, playbooks
  90_logs/automation-log.md  # companion run log
  templates/           # daily-note, weekly-review, project-brief, memory-entry templates
```

Only `SCAFFOLD.md`, `setup.sh`, and `SOUL.md` are tracked by git. Everything else is gitignored.

### Core Modules (src/apple_flow/)

| Module | Responsibility |
|--------|---------------|
| `__main__.py` | CLI entry point (`python -m apple_flow`), daemon lock management |
| `daemon.py` | Main polling loop, graceful shutdown, signal handling, connector selection |
| `orchestrator.py` | Command routing, approval gates, prompt construction, attachment handling |
| `commanding.py` | Parses command prefixes (idea:, plan:, task:, @alias extraction, CommandKind enum) |
| `ingress.py` | Reads from macOS Messages chat.db (read-only SQLite, attachment extraction) |
| `egress.py` | Sends iMessages via AppleScript, deduplicates outbound messages |
| `policy.py` | Sender allowlist, rate limiting enforcement |
| `store.py` | Thread-safe SQLite with connection caching and indexes |
| `config.py` | Pydantic settings with `apple_flow_` env prefix, path resolution |
| `codex_cli_connector.py` | Stateless CLI connector using `codex exec` (default, avoids state corruption) |
| `claude_cli_connector.py` | Stateless CLI connector using `claude -p` |
| `gemini_cli_connector.py` | Stateless CLI connector using `gemini -p` |
| `cline_connector.py` | Agentic CLI connector using `cline -y` |
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
| `companion.py` | CompanionLoop: proactive observation loop — stale approvals, calendar events, overdue reminders, office inbox; synthesizes via AI, sends iMessages; daily digest, weekly review, quiet hours, rate limiting, mute/unmute, cross-channel correlation |
| `memory.py` | FileMemory: reads/writes `agent-office/MEMORY.md` and `agent-office/60_memory/*.md` topic files; injected into AI prompts before each turn |
| `scheduler.py` | FollowUpScheduler: SQLite-backed `scheduled_actions` table for time-triggered follow-ups after task completions |
| `ambient.py` | AmbientScanner: passively reads Notes/Calendar/Mail every 15 min for context enrichment, writes to memory topics; never sends messages |

### Command Types

- **Non-mutating** (execute immediately): `relay:`, `idea:`, `plan:`
- **Mutating** (require approval): `task:`, `project:`
- **Control**: `approve <id>`, `deny <id>`, `deny all`, `status`, `clear context`
- **Dashboard**: `health:` (daemon stats, uptime, session count)
- **Memory**: `history:` (recent messages), `history: <query>` (search messages)
- **Workspace routing**: `@alias` prefix on any command (e.g. `task: @web-app deploy`)
- **Companion control**: `system: mute` (silence proactive messages), `system: unmute` (re-enable proactive messages)

### Key Safety Invariants

- `only_poll_allowed_senders=true` filters at SQL query time
- `require_chat_prefix=true` ignores messages without `relay:` prefix (default: false — natural language mode)
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
| `scheduled_actions` | Time-triggered follow-ups managed by FollowUpScheduler (`scheduler.py`) |

## Configuration

All settings use `apple_flow_` env prefix. Key settings in `.env`:

### Core Settings

- `apple_flow_allowed_senders` - comma-separated phone numbers (E.164 format)
- `apple_flow_allowed_workspaces` - paths Codex may access (auto-resolved to absolute)
- `apple_flow_default_workspace` - default working directory for Codex
- `apple_flow_messages_db_path` - usually `~/Library/Messages/chat.db`

### Safety Settings

- `apple_flow_only_poll_allowed_senders` - filter at SQL query time (default: true)
- `apple_flow_require_chat_prefix` - require `relay:` prefix on messages (default: false)
- `apple_flow_chat_prefix` - custom prefix string (default: "relay:")
- `apple_flow_approval_ttl_minutes` - how long approvals remain valid (default: 20)
- `apple_flow_max_messages_per_minute` - rate limit per sender (default: 30)

### Connector Settings

- `apple_flow_connector` - connector to use: `"codex-cli"` (default), `"claude-cli"`, `"gemini-cli"`, `"cline"`, `"codex-app-server"` (deprecated)
- `apple_flow_codex_turn_timeout_seconds` - timeout for all connectors (default: 300s/5min)

**Codex CLI** (`connector=codex-cli`, requires `codex login`):
- `apple_flow_codex_cli_command` - path to codex binary (default: "codex")
- `apple_flow_codex_cli_context_window` - recent exchanges to include as context (default: 10)
- `apple_flow_codex_cli_model` - model flag (e.g. `gpt-5.3-codex`; empty = codex default)

**Claude Code CLI** (`connector=claude-cli`, requires `claude auth login`):
- `apple_flow_claude_cli_command` - path to claude binary (default: "claude")
- `apple_flow_claude_cli_context_window` - recent exchanges to include as context (default: 10)
- `apple_flow_claude_cli_model` - model flag (e.g. `claude-sonnet-4-6`, `claude-opus-4-6`; empty = claude default)
- `apple_flow_claude_cli_dangerously_skip_permissions` - pass `--dangerously-skip-permissions` (default: true)
- `apple_flow_claude_cli_tools` - comma-separated values passed to `--tools` (optional, e.g. `default,WebSearch`)
- `apple_flow_claude_cli_allowed_tools` - comma-separated values passed to `--allowedTools` (optional, e.g. `WebSearch`)

**Gemini CLI** (`connector=gemini-cli`, requires `gemini auth login`):
- `apple_flow_gemini_cli_command` - path to gemini binary (default: "gemini")
- `apple_flow_gemini_cli_context_window` - recent exchanges to include as context (default: 10)
- `apple_flow_gemini_cli_model` - model flag (default: `gemini-3-flash-preview`)

**Cline CLI** (`connector=cline`, supports any model):
- `apple_flow_cline_command` - path to cline binary (default: "cline")
- `apple_flow_cline_model` - model to use (e.g. `claude-sonnet-4-5-20250929`, `gpt-4o`, `deepseek-v3`; empty = cline default)
- `apple_flow_cline_workspace` - workspace directory for cline (default: from `default_workspace`)
- `apple_flow_cline_timeout` - timeout in seconds (default: 300)

**Legacy app-server** (`connector=codex-app-server`, deprecated):
- `apple_flow_codex_app_server_cmd` - app-server command
- `apple_flow_use_codex_cli` - legacy boolean (still respected if `connector` is unset)

### Apple Mail Integration

- `apple_flow_enable_mail_polling` - enable Apple Mail as additional ingress (default: false)
- `apple_flow_mail_poll_account` - Mail.app account name to poll (empty = all/inbox)
- `apple_flow_mail_poll_mailbox` - mailbox to poll (default: INBOX)
- `apple_flow_mail_from_address` - sender address for outbound replies (empty = default)
- `apple_flow_mail_allowed_senders` - comma-separated email addresses to accept
- `apple_flow_mail_max_age_days` - only process emails from last N days (default: 2)
- `apple_flow_mail_signature` - signature appended to all email replies (default: "Apple Flow 🤖, Your 24/7 Assistant")

### Apple Reminders Integration

- `apple_flow_enable_reminders_polling` - enable Apple Reminders as task queue ingress (default: false)
- `apple_flow_reminders_list_name` - Reminders list to poll (default: "agent-task")
- `apple_flow_reminders_owner` - sender identity for reminder tasks (e.g. phone number; defaults to first allowed_sender)
- `apple_flow_reminders_auto_approve` - skip approval gate for reminder tasks (default: false)
- `apple_flow_reminders_poll_interval_seconds` - poll interval for Reminders (default: 5s)

### Apple Notes Integration

- `apple_flow_enable_notes_polling` - enable Apple Notes as long-form task ingress (default: false)
- `apple_flow_notes_folder_name` - Notes folder to poll (default: "agent-task")
- `apple_flow_notes_owner` - sender identity for note tasks (defaults to first allowed_sender)
- `apple_flow_notes_auto_approve` - skip approval gate for note tasks (default: false)
- `apple_flow_notes_poll_interval_seconds` - poll interval for Notes (default: 10s)
- `apple_flow_notes_fetch_timeout_seconds` - AppleScript fetch timeout per Notes poll (default: 20s)
- `apple_flow_notes_fetch_retries` - retry count after Notes fetch timeout (default: 1)
- `apple_flow_notes_fetch_retry_delay_seconds` - delay between Notes fetch retries (default: 1.5s)

### Apple Calendar Integration

- `apple_flow_enable_calendar_polling` - enable Apple Calendar as scheduled task ingress (default: false)
- `apple_flow_calendar_name` - Calendar to poll (default: "agent-schedule")
- `apple_flow_calendar_owner` - sender identity for calendar tasks (defaults to first allowed_sender)
- `apple_flow_calendar_auto_approve` - skip approval gate for calendar tasks (default: false)
- `apple_flow_calendar_poll_interval_seconds` - poll interval for Calendar (default: 30s)
- `apple_flow_calendar_lookahead_minutes` - how far ahead to look for due events (default: 5)

### Advanced Features

- `apple_flow_workspace_aliases` - JSON dict mapping @alias names to workspace paths (default: empty)
- `apple_flow_auto_context_messages` - number of recent messages to auto-inject as context (default: 10)
- `apple_flow_enable_progress_streaming` - send periodic progress updates during long tasks (default: false)
- `apple_flow_progress_update_interval_seconds` - minimum seconds between progress updates (default: 30)
- `apple_flow_enable_attachments` - enable reading inbound file attachments (default: false)
- `apple_flow_max_attachment_size_mb` - max attachment size to process (default: 10)
- `apple_flow_attachment_temp_dir` - temp directory for attachment processing (default: /tmp/apple_flow_attachments)

### Agent Office

- `apple_flow_soul_file` - path to companion SOUL.md injected as claude-cli system prompt (default: "agent-office/SOUL.md")

### Companion Layer

- `apple_flow_enable_companion` - enable the CompanionLoop proactive observation loop (default: false)
- `apple_flow_companion_poll_interval_seconds` - how often the companion checks for observations (default: 300)
- `apple_flow_companion_max_proactive_per_hour` - rate limit on proactive iMessages (default: 4)
- `apple_flow_companion_quiet_hours_start` - start of quiet hours, no proactive messages (default: "22:00")
- `apple_flow_companion_quiet_hours_end` - end of quiet hours (default: "07:00")
- `apple_flow_companion_stale_approval_minutes` - minutes before an approval is considered stale (default: 30)
- `apple_flow_companion_calendar_lookahead_minutes` - how far ahead to look for upcoming events (default: 60)
- `apple_flow_companion_enable_daily_digest` - write a daily digest note to agent-office/10_daily/ (default: false)
- `apple_flow_companion_digest_time` - time of day to generate the daily digest (default: "08:00")
- `apple_flow_companion_weekly_review_day` - day of week for weekly review (default: "sunday")
- `apple_flow_companion_weekly_review_time` - time of day for weekly review (default: "20:00")

### Memory

- `apple_flow_enable_memory` - inject FileMemory (MEMORY.md + topic files) into AI prompts (default: false)
- `apple_flow_memory_max_context_chars` - maximum characters of memory to inject per turn (default: 2000)

### Follow-Up Scheduler

- `apple_flow_enable_follow_ups` - enable time-triggered follow-up nudges after task completions (default: false)
- `apple_flow_default_follow_up_hours` - default delay before a follow-up is sent (default: 2.0)
- `apple_flow_max_follow_up_nudges` - maximum follow-up messages per task (default: 3)

### Ambient Scanner

- `apple_flow_enable_ambient_scanning` - enable passive context enrichment from Notes/Calendar/Mail (default: false)
- `apple_flow_ambient_scan_interval_seconds` - how often the ambient scanner runs (default: 900)

See `.env.example` for full list. **When adding a new config field:** update both `config.py` and `.env.example`, add docs to `README.md`, and ensure a sensible default.

## Admin API

The admin API runs on port 8787 by default (`python -m apple_flow admin`). Set `apple_flow_admin_api_token` to a secret string to require `Authorization: Bearer <token>` on all endpoints except `/health`.

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
tests/test_cli_connector.py       # Stateless CLI connector (codex exec)
tests/test_admin_api.py           # FastAPI admin endpoints

# Autonomous Companion Layer
tests/test_companion.py           # CompanionLoop: proactive observations, quiet hours, rate limiting, mute/unmute (58 tests)
tests/test_memory.py              # FileMemory: MEMORY.md and topic file read/write, prompt injection (14 tests)
tests/test_scheduler.py           # FollowUpScheduler: scheduled_actions CRUD, nudge dispatch (14 tests)
tests/test_ambient.py             # AmbientScanner: passive context enrichment, memory topic writes (11 tests)
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
- Authentication for your chosen connector (run once):
  - `codex login` — if using `apple_flow_connector=codex-cli` (default)
  - `claude auth login` — if using `apple_flow_connector=claude-cli`
  - `gemini auth login` — if using `apple_flow_connector=gemini-cli`
- For Apple Mail integration: Apple Mail configured and running on this Mac
- For Apple Reminders integration: Reminders.app on this Mac, a list named per config (default: "Codex Tasks")
- For Apple Notes integration: Notes.app on this Mac, a folder named per config (default: "Codex Inbox")
- For Apple Calendar integration: Calendar.app on this Mac, a calendar named per config (default: "Codex Schedule")

## Service Management (launchd)

```bash
# Start/stop service
launchctl start local.apple-flow
launchctl stop local.apple-flow

# Check service status
launchctl list local.apple-flow

# View logs (all Python logging goes to stderr)
tail -f logs/apple-flow.err.log
```

## Conventions for AI Assistants

### After any behavior change
Always run `pytest -q` to verify tests pass before considering the task complete.

### Adding a new Apple app integration
Follow the established pattern: create `<app>_ingress.py` and `<app>_egress.py`, add config fields to `config.py` and `.env.example`, wire up in `daemon.py`, and add test files `tests/test_<app>_ingress.py` and `tests/test_<app>_egress.py`.

### Adding a new config field
1. Add the field with a default to `src/apple_flow/config.py`
2. Add the commented example to `.env.example`
3. Document it in `README.md`
4. Update `CLAUDE.md` (this file) if it's a key setting

### Adding a new command type
1. Add the variant to `CommandKind` enum in `models.py`
2. Parse it in `commanding.py`
3. Handle it in `orchestrator.py`
4. Add tests to `tests/test_command_parser.py` and `tests/test_orchestrator.py`

### Connector selection
- `"codex-cli"` (default): `codex_cli_connector.py` — stateless `codex exec`, requires `codex login`
- `"claude-cli"`: `claude_cli_connector.py` — stateless `claude -p`, requires `claude auth login`
- `"gemini-cli"`: `gemini_cli_connector.py` — stateless `gemini -p`, requires `gemini auth login`
- `"cline"`: `cline_connector.py` — agentic `cline -y`, supports any model provider (OpenAI, Anthropic, Google, DeepSeek, etc.)
- `"codex-app-server"` (deprecated): `codex_connector.py` — stateful JSON-RPC, prone to state corruption
- Selection controlled by `apple_flow_connector` config field (falls back to `apple_flow_use_codex_cli` for backwards compat)

### Key patterns
- All async I/O uses `asyncio`; test with `pytest-asyncio` (`asyncio_mode = "auto"`)
- Phone number normalization via `utils.normalize_sender()` for consistent sender IDs
- AppleScript calls are the mechanism for all Apple app interactions (Mail, Reminders, Notes, Calendar)
- Store operations are thread-safe via connection caching in `store.py`
- Protocol interfaces in `protocols.py` enable fake implementations for tests

## Project Statistics

| Metric | Value |
|--------|-------|
| Source modules | 30 |
| Test files | 38 |
| Tests passing | 487 |
| Config options | 60+ |
| Python requirement | ≥3.11 |
| Core dependencies | fastapi, uvicorn, pydantic, pydantic-settings, httpx |
| Dev dependencies | pytest, pytest-asyncio, httpx |
