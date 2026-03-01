# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project Overview

Apple Flow is a local-first macOS daemon that bridges iMessage, Apple Mail, Apple Reminders, Apple Notes, and Apple Calendar to AI coding agents (Codex CLI, Claude Code, Gemini CLI, Cline, or any compatible connector). It polls the local Messages database and (optionally) Apple Mail, Reminders, Notes, and Calendar for inbound messages/tasks, routes allowlisted senders to the configured AI agent, enforces approval workflows for mutating operations, and replies via AppleScript.

The project also ships an optional **Autonomous Companion Layer**: a proactive loop (`companion.py`) that watches for stale approvals, upcoming calendar events, overdue reminders, and office inbox items, synthesizes observations via AI, and sends proactive iMessages. Companion state is anchored in `agent-office/` — a structured workspace directory that holds the companion's identity (`SOUL.md`), durable memory (`MEMORY.md`), topic memory files, daily notes, project briefs, and automation playbooks.

**Python:** >=3.11 | **Package name:** `apple-flow`

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
iMessage DB -> Ingress -> Policy -> Orchestrator -> Connector -> Egress -> AppleScript iMessage
                                        |
                                      Store (SQLite state + approvals)

Apple Mail -> MailIngress -> Orchestrator -> Connector -> MailEgress -> AppleScript Mail.app
  (optional, polls unread)                                 (sends reply emails)

Reminders.app -> RemindersIngress -> Orchestrator -> Connector -> iMessage Egress (approvals)
  (optional, polls incomplete)            |                            |
                                        Store           RemindersEgress -> annotate/complete reminder

Notes.app -> NotesIngress -> Orchestrator -> Connector -> iMessage Egress (approvals)
  (optional, polls folder)        |                            |
                                Store             NotesEgress -> append result to note

Calendar.app -> CalendarIngress -> Orchestrator -> Connector -> iMessage Egress (approvals)
  (optional, polls due events)        |                              |
                                    Store           CalendarEgress -> annotate event description

POST /task -> FastAPI -> Orchestrator -> Connector -> iMessage Egress
  (Siri Shortcuts / curl bridge)

CompanionLoop -> (stale approvals, calendar, reminders, office inbox) -> AI synthesis -> iMessage Egress
  (optional, proactive; respects quiet hours + rate limit)       |
                                                        FollowUpScheduler (scheduled_actions table)

AmbientScanner -> Notes/Calendar/Mail -> FileMemory (agent-office/60_memory/)
  (optional, passive context enrichment every 15 min; never sends messages)
```

### Agent Office Directory (agent-office/)

The companion's workspace, checked into the repo as a scaffold. Personal content is gitignored.

```
agent-office/
  SOUL.md              # companion identity/personality -- injected into system prompt
  MEMORY.md            # durable memory -- injected into every AI prompt (when enable_memory=true)
  SCAFFOLD.md          # describes the directory structure (tracked by git)
  setup.sh             # idempotent bootstrap script -- run once after cloning
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
| `cline_connector.py` | Agentic CLI connector using `cline -y`, supports any model provider |
| `main.py` | FastAPI admin endpoints (/health, /sessions, /approvals, /audit/events, POST /task) |
| `admin_client.py` | Admin API client library (programmatic access to admin endpoints) |
| `protocols.py` | Protocol interfaces for type-safe component injection (StoreProtocol, ConnectorProtocol, EgressProtocol) |
| `models.py` | Data models and enums (RunState, ApprovalStatus, CommandKind, InboundMessage, ApprovalRequest) |
| `utils.py` | Shared utilities (normalize_sender) |
| `apple_tools.py` | AppleScript tool implementations for Apple app interactions |
| `approval.py` | Approval workflow logic |
| `mail_ingress.py` | Reads unread emails from Apple Mail via AppleScript |
| `mail_egress.py` | Sends threaded reply emails via Apple Mail AppleScript with signatures |
| `reminders_ingress.py` | Polls Apple Reminders for incomplete tasks via AppleScript |
| `reminders_egress.py` | Writes results back to reminders and marks them complete |
| `notes_ingress.py` | Polls Apple Notes folder for new notes via AppleScript |
| `notes_egress.py` | Appends results back to note body |
| `notes_logging.py` | Logging integration for Apple Notes |
| `calendar_ingress.py` | Polls Apple Calendar for due events via AppleScript |
| `calendar_egress.py` | Writes results into event description/notes |
| `office_sync.py` | Syncs agent-office state |
| `companion.py` | CompanionLoop: proactive observation loop -- stale approvals, calendar events, overdue reminders, office inbox; synthesizes via AI, sends iMessages; daily digest, weekly review, quiet hours, rate limiting, mute/unmute |
| `memory.py` | FileMemory: reads/writes `agent-office/MEMORY.md` and `agent-office/60_memory/*.md` topic files; injected into AI prompts before each turn |
| `scheduler.py` | FollowUpScheduler: SQLite-backed `scheduled_actions` table for time-triggered follow-ups after task completions |
| `ambient.py` | AmbientScanner: passively reads Notes/Calendar/Mail every 15 min for context enrichment, writes to memory topics; never sends messages |

## Data Models

### Enums (models.py)

```python
class RunState(str, Enum):
    RECEIVED, PLANNING, AWAITING_APPROVAL, QUEUED, RUNNING, EXECUTING,
    VERIFYING, CHECKPOINTED, COMPLETED, FAILED, DENIED, CANCELLED

class ApprovalStatus(str, Enum):
    PENDING, APPROVED, DENIED, EXPIRED

class CommandKind(str, Enum):
    CHAT, IDEA, PLAN, TASK, PROJECT, CLEAR_CONTEXT,
    APPROVE, DENY, DENY_ALL, STATUS, HEALTH, HISTORY, USAGE, SYSTEM, LOGS
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

## Command Types

- **Non-mutating** (execute immediately): `<anything>`, `relay:` (when prefix mode enabled), `idea:`, `plan:`
- **Mutating** (require approval): `task:`, `project:`
- **Control**: `approve <id>`, `deny <id>`, `deny all`, `status`, `clear context`
- **Dashboard**: `health` (daemon stats, uptime, session count)
- **Memory**: `history:` (recent messages), `history: <query>` (search messages)
- **Workspace routing**: `@alias` prefix on any command (e.g. `task: @web-app deploy`)
- **Companion control**: `system: mute` (silence proactive messages), `system: unmute` (re-enable)
- **Tooling controls**: `logs`, `usage`, `system: stop`, `system: restart`, `system: kill provider`, `system: cancel run <run_id>`, `system: killswitch`

## Safety Invariants

- `only_poll_allowed_senders=true` filters at SQL query time
- `require_chat_prefix=true` ignores messages without `relay:` prefix
- Mutating commands always go through approval workflow
- **Approval sender verification**: only the original requester can approve/deny their requests
- Duplicate outbound suppression prevents echo loops
- Graceful shutdown with SIGINT/SIGTERM handling
- iMessage DB opened in read-only mode (`PRAGMA query_only`, URI read-only)
- Daemon lock file prevents multiple concurrent instances
- Rate limiting enforced per sender (`max_messages_per_minute`)

## Configuration

All settings use the `apple_flow_` env prefix. Configured via `.env` file.

### Core Settings

- `apple_flow_allowed_senders` -- comma-separated phone numbers (E.164 format)
- `apple_flow_allowed_workspaces` -- paths the AI agent may access (auto-resolved to absolute)
- `apple_flow_default_workspace` -- default working directory
- `apple_flow_messages_db_path` -- usually `/Users/<you>/Library/Messages/chat.db` (absolute path)

### Safety Settings

- `apple_flow_only_poll_allowed_senders` -- filter at SQL query time (default: true)
- `apple_flow_require_chat_prefix` -- require `relay:` prefix on messages (default: false)
- `apple_flow_chat_prefix` -- custom prefix string (default: "relay:")
- `apple_flow_approval_ttl_minutes` -- how long approvals remain valid (default: 20)
- `apple_flow_max_messages_per_minute` -- rate limit per sender (default: 30)

### Connector Settings

- `apple_flow_connector` -- connector to use: `"codex-cli"` (default), `"claude-cli"`, `"gemini-cli"`, `"cline"`, `"kilo-cli"`
- `apple_flow_codex_turn_timeout_seconds` -- timeout for all connectors (default: 300s/5min)

Connector-specific settings (CLI binary path, model, context window, etc.) are documented in `.env.example`. See also the **Connector selection** section under Development Conventions below.

### Additional Integrations

Apple Mail, Reminders, Notes, Calendar, Companion, Memory, Follow-Up Scheduler, and Ambient Scanner each have their own config sections. All are disabled by default (opt-in via `.env`).

See `.env.example` for the full 60+ field list with descriptions. **When adding a new config field:** update both `config.py` and `.env.example`, add docs to `README.md`, and ensure a sensible default.

### Memory v2 (Canonical Memory)

New in v0.3.1 — SQLite-backed canonical memory with shadow-mode rollout:

- `apple_flow_enable_memory_v2` — enable canonical memory retrieval (default: false)
- `apple_flow_memory_v2_shadow_mode` — compute canonical retrieval but keep legacy injection; logs diff metrics (default: false)
- `apple_flow_memory_v2_migrate_on_start` — backfill canonical memory from legacy files on startup (default: true)
- `apple_flow_memory_v2_db_path` — canonical memory DB path; empty uses `<agent-office>/.apple-flow-memory.sqlite3`
- `apple_flow_memory_v2_scope` — retrieval scope selector (default: global)
- `apple_flow_memory_v2_maintenance_interval_seconds` — maintenance interval (default: 3600)
- `apple_flow_memory_max_storage_mb` — best-effort storage cap (default: 256)
- `apple_flow_memory_v2_include_legacy_fallback` — fallback to legacy if canonical empty (default: true)

## Admin API

The admin API runs on port 8787 by default (`python -m apple_flow admin`).

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/sessions` | GET | List active sender threads |
| `/approvals/pending` | GET | List pending approval requests |
| `/audit/events` | GET | Audit log |
| `/task` | POST | Submit a task programmatically (Siri Shortcuts / curl) |
| `/metrics` | GET | Basic runtime metrics |

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
tests/test_apple_tools.py       # AppleScript tool implementations

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

# Connectors
tests/test_cli_connector.py     # Stateless CLI connector (codex exec)
tests/test_gemini_cli_connector.py  # Stateless Gemini CLI connector (gemini -p)
tests/test_cline_connector.py   # Cline CLI connector

# Features
tests/test_workspace_routing.py   # Multi-workspace @alias routing
tests/test_health_dashboard.py    # Health command, daemon statistics
tests/test_conversation_memory.py # History command + auto-context injection
tests/test_siri_shortcuts.py      # POST /task admin API endpoint
tests/test_progress_streaming.py  # Incremental progress updates
tests/test_attachments.py         # File attachment support
tests/test_admin_api.py           # FastAPI admin endpoints
tests/test_office_sync.py         # Agent-office sync

# Autonomous Companion Layer
tests/test_companion.py           # CompanionLoop: proactive observations, quiet hours, rate limiting, mute/unmute
tests/test_memory.py              # FileMemory: MEMORY.md and topic file read/write, prompt injection
tests/test_scheduler.py           # FollowUpScheduler: scheduled_actions CRUD, nudge dispatch
tests/test_ambient.py             # AmbientScanner: passive context enrichment, memory topic writes
```

## Security Model

- **Sender allowlist**: Only messages from configured senders are processed
- **Approval workflow**: Mutating operations (task:, project:) require explicit approval
- **Sender verification**: Approvals can only be granted/denied by the original requester
- **Workspace restrictions**: The AI agent can only access paths in `allowed_workspaces`
- **Read-only iMessage DB**: Opened with `PRAGMA query_only` and URI read-only mode
- **Rate limiting**: Configurable max messages per minute per sender
- **Daemon lock**: Prevents multiple concurrent instances from running

## Prerequisites

- macOS with iMessage signed in
- Full Disk Access granted to terminal app (for reading chat.db)
- Authentication for your chosen connector (run once):
  - `codex login` -- if using `apple_flow_connector=codex-cli` (default)
  - `claude auth login` -- if using `apple_flow_connector=claude-cli`
  - `gemini auth login` -- if using `apple_flow_connector=gemini-cli`
  - No auth needed for `cline` (uses its own config)
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

## Development Conventions

### After any behavior change

Always run `pytest -q` to verify tests pass before considering the task complete.

### Adding a new Apple app integration

Follow the established pattern: create `<app>_ingress.py` and `<app>_egress.py`, add config fields to `config.py` and `.env.example`, wire up in `daemon.py`, and add test files `tests/test_<app>_ingress.py` and `tests/test_<app>_egress.py`.

### Adding a new config field

1. Add the field with a default to `src/apple_flow/config.py`
2. Add the commented example to `.env.example`
3. Document it in `README.md`
4. Update `AGENTS.md` / `CLAUDE.md` if it's a key setting

### Adding a new command type

1. Add the variant to `CommandKind` enum in `models.py`
2. Parse it in `commanding.py`
3. Handle it in `orchestrator.py`
4. Add tests to `tests/test_command_parser.py` and `tests/test_orchestrator.py`

### Connector selection

- `"codex-cli"` (default): `codex_cli_connector.py` -- stateless `codex exec`, requires `codex login`
- `"claude-cli"`: `claude_cli_connector.py` -- stateless `claude -p`, requires `claude auth login`
- `"gemini-cli"`: `gemini_cli_connector.py` -- stateless `gemini -p`, requires `gemini auth login`
- `"cline"`: `cline_connector.py` -- agentic `cline -y`, supports any model provider (OpenAI, Anthropic, Google, DeepSeek, etc.)
- Selection controlled by `apple_flow_connector` config field

### Key patterns

- All async I/O uses `asyncio`; test with `pytest-asyncio` (`asyncio_mode = "auto"`)
- Phone number normalization via `utils.normalize_sender()` for consistent sender IDs
- AppleScript calls are the mechanism for all Apple app interactions (Mail, Reminders, Notes, Calendar)
- Store operations are thread-safe via connection caching in `store.py`
- Protocol interfaces in `protocols.py` enable fake implementations for tests

### Logging expectations

- Terminal logs should clearly show: inbound row processed or ignored, ignore reason (echo/prefix/empty/etc.), handled command kind and duration
- Avoid noisy spam logs; prefer actionable logs

### Safety-first defaults

- Never disable sender allowlist by default
- Keep `apple_flow_only_poll_allowed_senders=true`
- Keep `apple_flow_require_chat_prefix=false` unless explicitly requested
- Keep mutating workflows behind approval (`task:` / `project:`)
- Respect duplicate outbound suppression; do not remove echo suppression without explicit request

## Skills

A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill.

### Available skills

- skill-creator: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends capabilities with specialized knowledge, workflows, or tool integrations. (file: /Users/cypher-server/.codex/skills/.system/skill-creator/SKILL.md)
- skill-installer: Install skills into $CODEX_HOME/skills from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos). (file: /Users/cypher-server/.codex/skills/.system/skill-installer/SKILL.md)

### How to use skills

- Discovery: The list above is the skills available in this session (name + description + file path). Skill bodies live on disk at the listed paths.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.py`), resolve them relative to the skill directory listed above first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue.
