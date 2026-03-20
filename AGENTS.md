# AGENTS.md

Canonical AI-agent guide for this repository.

Last updated: 2026-03-19
Version: 0.6.0
Python: >=3.11
Package: `apple-flow`

## Purpose

Apple Flow is a local-first macOS daemon that bridges iMessage, Apple Mail, Apple Reminders, Apple Notes, Apple Calendar, and the Admin API to AI connectors. It routes inbound work through policy checks, orchestration, connector execution, and channel-specific egress, with approval gates for mutating work.

Use this file as the repo-wide source of truth for AI contributors. `CLAUDE.md` and `GEMINI.md` should stay aligned with this file and only add small platform-specific notes.

## Read First

Start with these docs before making non-trivial changes:

1. `README.md`
2. `docs/PROJECT_REFERENCE.md`
3. `docs/ENV_SETUP.md`
4. `SECURITY.md`

Use these setup guides when needed:

- `docs/AI_INSTALL_MASTER_PROMPT.md`
- `docs/QUICKSTART.md`
- `docs/AUTO_START_SETUP.md`

## Common Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# Tests
pytest -q
pytest tests/test_orchestrator.py -v
pytest tests/test_admin_api.py -v

# Run locally
python -m apple_flow daemon
python -m apple_flow admin
python -m apple_flow version

# Setup helpers
./scripts/start_beginner.sh
./scripts/setup_autostart.sh
./scripts/uninstall_autostart.sh

# Tool surface
python -m apple_flow tools --list
```

## CLI Surface

`python -m apple_flow` supports these top-level modes:

- `daemon`
- `admin`
- `tools`
- `setup`
- `wizard`
- `config`
- `service`
- `version`

The tools subcommand exposes Apple-app automation helpers for Notes, Mail, Messages, Reminders, Calendar, Numbers, and Pages through `src/apple_flow/apple_tools.py`.

## Architecture Snapshot

```text
iMessage DB -> Ingress -> Policy -> Orchestrator -> Connector -> Egress -> AppleScript iMessage
                                        |
                                      Store (SQLite state + approvals)

Apple Mail -> MailIngress -> Orchestrator -> Connector -> MailEgress -> Apple Mail
Reminders.app -> RemindersIngress -> Orchestrator -> Connector -> RemindersEgress / iMessage approvals
Notes.app -> NotesIngress -> Orchestrator -> Connector -> NotesEgress / iMessage approvals
Calendar.app -> CalendarIngress -> Orchestrator -> Connector -> CalendarEgress / iMessage approvals
POST /task -> FastAPI Admin API -> Orchestrator -> Connector -> Egress

CompanionLoop -> proactive observations -> Connector -> iMessage egress
AmbientScanner -> passive context enrichment -> FileMemory / Memory v2
FollowUpScheduler -> scheduled nudges and follow-up actions
```

## Important Modules

| Path | Responsibility |
| --- | --- |
| `src/apple_flow/__main__.py` | CLI entry point and command dispatch |
| `src/apple_flow/daemon.py` | Main runtime loop, connector wiring, background services |
| `src/apple_flow/orchestrator.py` | Command routing, approval gates, prompt construction, task lifecycle |
| `src/apple_flow/commanding.py` | User-facing command parsing and `CommandKind` definitions |
| `src/apple_flow/store.py` | SQLite persistence for sessions, messages, runs, approvals, events, scheduled actions |
| `src/apple_flow/config.py` | `RelaySettings` and env-backed configuration |
| `src/apple_flow/main.py` | FastAPI Admin API |
| `src/apple_flow/ingress.py` / `egress.py` | iMessage ingress and egress |
| `src/apple_flow/mail_ingress.py` / `mail_egress.py` | Apple Mail gateway |
| `src/apple_flow/reminders_ingress.py` / `reminders_egress.py` | Apple Reminders gateway |
| `src/apple_flow/notes_ingress.py` / `notes_egress.py` / `notes_logging.py` | Apple Notes gateway and logging |
| `src/apple_flow/calendar_ingress.py` / `calendar_egress.py` | Apple Calendar gateway |
| `src/apple_flow/attachments.py` | Attachment extraction, OCR, Office parsing, audio transcription |
| `src/apple_flow/companion.py` | Proactive companion loop |
| `src/apple_flow/memory.py` / `memory_v2.py` | File memory and canonical SQLite-backed memory |
| `src/apple_flow/scheduler.py` | Follow-up scheduling |
| `src/apple_flow/ambient.py` | Passive context enrichment |
| `src/apple_flow/apple_tools.py` | Apple app automation tool implementations |
| `src/apple_flow/cli_control.py` / `setup_wizard.py` | Setup, validation, service control, doctor flows |

## Connectors

Supported connectors today:

- `codex-cli`
- `claude-cli`
- `gemini-cli`
- `kilo-cli`
- `cline`
- `ollama`

Relevant modules:

- `src/apple_flow/codex_cli_connector.py`
- `src/apple_flow/claude_cli_connector.py`
- `src/apple_flow/gemini_cli_connector.py`
- `src/apple_flow/kilo_cli_connector.py`
- `src/apple_flow/cline_connector.py`
- `src/apple_flow/ollama_connector.py`

If connector behavior changes, update docs in this file, `CLAUDE.md`, `GEMINI.md`, `README.md`, and the relevant setup docs.

## Command Model

User-facing command kinds are parsed in `src/apple_flow/commanding.py`.

- Natural chat or `relay:`: non-mutating turn
- `idea:`: brainstorming
- `plan:`: planning-only response
- `task:`: mutating execution, approval-gated
- `project:`: larger mutating execution, approval-gated
- `voice:`: approval-gated spoken iMessage response
- `voice-task:`: approval-gated task followed by text + voice response
- `help`, `health`, `history:`, `usage`, `logs`, `status`
- `approve <id>`, `deny <id>`, `deny all`
- `system: ...`: runtime controls like mute/unmute, helper maintenance, stop/restart, provider cleanup

Workspace routing uses `@alias`, backed by `apple_flow_workspace_aliases`.

## Runtime State

Primary runtime state lives in SQLite. Key tables:

- `sessions`
- `messages`
- `runs`
- `approvals`
- `events`
- `kv_state`
- `scheduled_actions`

Run lifecycle states live in `src/apple_flow/models.py` under `RunState`.

## Admin API

The Admin API is served by `src/apple_flow/main.py` and defaults to `127.0.0.1:8787`.

Current endpoints:

- `GET /health`
- `GET /sessions`
- `GET /runs/{run_id}`
- `GET /approvals/pending`
- `POST /approvals/{request_id}/override`
- `GET /metrics`
- `GET /audit/events`
- `POST /task`

When `apple_flow_admin_api_token` is set, every route except `/health` requires `Authorization: Bearer <token>`.

## Configuration Hotspots

Configuration lives in `.env` and `RelaySettings` with the `apple_flow_` prefix.

Baseline keys:

- `apple_flow_allowed_senders`
- `apple_flow_allowed_workspaces`
- `apple_flow_default_workspace`
- `apple_flow_connector`
- `apple_flow_db_path`
- `apple_flow_messages_db_path`

Important groups to know:

- Safety: `only_poll_allowed_senders`, `approval_ttl_minutes`, `max_messages_per_minute`, `require_chat_prefix`
- Connectors: connector-specific command/model/context options
- Routing: `workspace_aliases`, `file_aliases`
- Gateways: mail/reminders/notes/calendar enable flags and resource names
- Companion and memory: `enable_companion`, `enable_memory`, `enable_memory_v2`, `enable_follow_ups`, `enable_ambient_scanning`
- Attachments and voice: attachment limits, OCR/transcription, phone TTS settings
- Logging and audit: `log_file_path`, `enable_csv_audit_log`, `csv_audit_log_path`

Canonical configuration references:

- `.env.example`
- `docs/ENV_SETUP.md`
- `docs/PROJECT_REFERENCE.md`

## Safety Invariants

Do not weaken these defaults without an explicit request and a corresponding doc update:

- Sender allowlisting stays enabled by default.
- Mutating work stays behind approvals.
- Approval sender verification remains enforced.
- Workspace access stays bounded by `allowed_workspaces`.
- iMessage DB access stays read-only.
- Duplicate outbound suppression stays on.
- Rate limiting stays enforced.
- Quiet-hours and proactive-rate protections stay intact when companion mode is enabled.

## Testing Expectations

The test suite is broad and includes orchestration, approvals, connectors, gateway integrations, setup flows, memory, scheduler, attachment handling, and admin API coverage.

Minimum expectation:

- Run `pytest -q` after any behavior change.
- Add or update tests for connector, orchestration, gateway, config, or security changes.

Useful targets:

```bash
pytest tests/test_orchestrator.py -v
pytest tests/test_admin_api.py -v
pytest tests/test_daemon_startup.py -v
pytest tests/test_setup_wizard.py -v
```

## Working Conventions For AI Agents

- Prefer `rg` and `rg --files` for search.
- Follow existing async and protocol-driven patterns before introducing new abstractions.
- Keep gateway changes deterministic and AppleScript-aware.
- Prefer updating canonical docs instead of duplicating long config matrices in multiple places.
- When changing config fields, update `src/apple_flow/config.py`, `.env.example`, `README.md`, and the relevant docs.
- When changing command kinds or admin endpoints, update this file, `CLAUDE.md`, `GEMINI.md`, `README.md`, and any docs that mention the surface.

## Docs Structure

- `docs/README.md` is the navigation index for repository docs.
- Top-level `docs/` should stay limited to user-facing setup docs and canonical project reference pages.
- Maintainer-only prompt packs, helper templates, and scheduled automation material belong under `docs/internal/`.
- Historical plans and superseded guides belong under `docs/archive/`.
- Do not add overlapping setup guides when an existing canonical page can be updated instead.

## File-Sync Policy

Keep these files aligned:

- `AGENTS.md` is the canonical repo-wide agent guide.
- `CLAUDE.md` should add Claude-specific notes but defer to `AGENTS.md`.
- `GEMINI.md` should add Gemini-specific notes but defer to `AGENTS.md`.

When facts drift, update all three in the same change.
