# Apple Flow Project Reference

**Module or component:** Apple Flow core project
**Version:** 0.6.0
**Last updated:** 2026-03-10
**Maintainer:** dkyazzentwatwa

## Overview

Apple Flow is a local-first macOS daemon that bridges Apple apps to AI coding assistants. It accepts inbound work from iMessage by default and can optionally ingest work from Apple Mail, Reminders, Notes, Calendar, or the local Admin API, then routes that work through policy checks, orchestration, connector execution, and app-specific egress.

This reference is the canonical high-level guide for contributors who need to understand how the system fits together. Use it alongside setup-focused guides such as [QUICKSTART.md](./QUICKSTART.md), [ENV_SETUP.md](./ENV_SETUP.md), [AUTO_START_SETUP.md](./AUTO_START_SETUP.md), and the operational safety details in [SECURITY.md](../SECURITY.md).

## Architecture And Components

### Runtime data flow

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

### Core modules

| Module | Responsibility |
| --- | --- |
| `src/apple_flow/__main__.py` | CLI entry point and process-level command dispatch |
| `src/apple_flow/daemon.py` | Main polling loop, startup, shutdown, connector wiring, background services |
| `src/apple_flow/orchestrator.py` | Command routing, approval gates, prompt construction, task lifecycle |
| `src/apple_flow/commanding.py` | Prefix parsing such as `idea:`, `plan:`, `task:`, `project:`, and `@alias` |
| `src/apple_flow/policy.py` | Sender allowlist and rate-limit enforcement |
| `src/apple_flow/store.py` | SQLite persistence for sessions, messages, runs, approvals, events, and scheduled actions |
| `src/apple_flow/main.py` | FastAPI Admin API (`/health`, `/sessions`, `/runs/{run_id}`, `/approvals/pending`, `/audit/events`, `/metrics`, `POST /task`) |
| `src/apple_flow/config.py` | Pydantic settings, path resolution, connector and gateway configuration |
| `src/apple_flow/ingress.py` / `egress.py` | iMessage ingress and outbound AppleScript delivery |
| `src/apple_flow/mail_ingress.py` / `mail_egress.py` | Apple Mail polling and threaded email replies |
| `src/apple_flow/reminders_ingress.py` / `reminders_egress.py` | Reminder task polling, annotation, and completion flows |
| `src/apple_flow/notes_ingress.py` / `notes_egress.py` / `notes_logging.py` | Note-driven task intake plus write-back and logging |
| `src/apple_flow/calendar_ingress.py` / `calendar_egress.py` | Calendar-triggered tasks and event annotation |
| `src/apple_flow/codex_cli_connector.py` | Stateless Codex CLI execution |
| `src/apple_flow/claude_cli_connector.py` | Stateless Claude CLI execution |
| `src/apple_flow/gemini_cli_connector.py` | Stateless Gemini CLI execution |
| `src/apple_flow/kilo_cli_connector.py` | Stateless Kilo CLI execution |
| `src/apple_flow/cline_connector.py` | Agentic Cline execution |
| `src/apple_flow/ollama_connector.py` | Native local Ollama chat integration |
| `src/apple_flow/companion.py` | Proactive companion loop with quiet hours and rate limits |
| `src/apple_flow/memory.py` / `memory_v2.py` | Legacy file memory plus canonical SQLite-backed memory |
| `src/apple_flow/scheduler.py` | Time-triggered follow-up scheduling |
| `src/apple_flow/ambient.py` | Passive context enrichment from local Apple data |
| `src/apple_flow/attachments.py` | Attachment extraction, OCR, Office parsing, and audio transcription support |

### State model

The SQLite store is the canonical runtime state layer. The main tables are:

| Table | Purpose |
| --- | --- |
| `sessions` | Active sender threads |
| `messages` | Processed inbound and outbound message tracking |
| `runs` | Execution records and lifecycle state |
| `approvals` | Pending and resolved approval requests |
| `events` | Audit trail |
| `kv_state` | Lightweight key-value runtime state |
| `scheduled_actions` | Follow-up scheduler queue |

## Command Surface

### User-facing command kinds

| Command | Behavior |
| --- | --- |
| Natural chat / `relay:` | Non-mutating conversational turn |
| `idea:` | Brainstorming mode |
| `plan:` | Planning-only response |
| `task:` | Mutating execution, approval-gated |
| `project:` | Larger mutating execution, approval-gated |
| `approve <id>` / `deny <id>` / `deny all` | Approval control |
| `status` / `health` / `history:` / `usage` / `logs` | Operational and introspection commands |
| `system: ...` | Runtime controls, mute/unmute, restart/stop, helper maintenance, provider cleanup |

### Workspace routing

Workspace aliases are configured with `apple_flow_workspace_aliases` in `.env`. Users can route a turn to a specific workspace with `@alias`, for example:

```text
task: @web-app deploy to staging
plan: @logs summarize the latest daemon failures
```

## Admin API

The Admin API is built with FastAPI and listens on `apple_flow_admin_host:apple_flow_admin_port` (default `127.0.0.1:8787`).

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | `GET` | Health status and gateway health summary |
| `/sessions` | `GET` | Active sessions |
| `/runs/{run_id}` | `GET` | Run lookup |
| `/approvals/pending` | `GET` | Pending approval requests |
| `/approvals/{request_id}/override` | `POST` | Admin approval override |
| `/audit/events` | `GET` | Audit event stream |
| `/metrics` | `GET` | Basic runtime counts |
| `/task` | `POST` | Programmatic task submission |

If `apple_flow_admin_api_token` is set, all routes except `/health` require `Authorization: Bearer <token>`.

## Configuration

Apple Flow uses `.env` or environment variables with the `apple_flow_` prefix. The full field list lives in [ENV_SETUP.md](./ENV_SETUP.md) and `.env.example`.

### Required baseline settings

| Variable | Why it matters |
| --- | --- |
| `apple_flow_allowed_senders` | Defines who can trigger work |
| `apple_flow_allowed_workspaces` | Defines filesystem boundaries |
| `apple_flow_default_workspace` | Sets the connector working directory |
| `apple_flow_connector` | Chooses the backend connector |
| `apple_flow_db_path` | Controls the runtime SQLite location |

### Major configuration areas

| Area | Representative settings |
| --- | --- |
| Core runtime | `apple_flow_poll_interval_seconds`, `apple_flow_codex_turn_timeout_seconds`, `apple_flow_max_concurrent_ai_calls` |
| Safety | `apple_flow_only_poll_allowed_senders`, `apple_flow_approval_ttl_minutes`, `apple_flow_max_messages_per_minute`, `apple_flow_require_chat_prefix` |
| Connectors | `apple_flow_connector` plus connector-specific command/model/context settings |
| Routing | `apple_flow_workspace_aliases`, `apple_flow_file_aliases` |
| Gateways | `apple_flow_enable_mail_polling`, `apple_flow_enable_reminders_polling`, `apple_flow_enable_notes_polling`, `apple_flow_enable_calendar_polling` |
| Companion and memory | `apple_flow_enable_companion`, `apple_flow_enable_memory`, `apple_flow_enable_memory_v2`, `apple_flow_enable_follow_ups`, `apple_flow_enable_ambient_scanning` |
| Attachments and voice | `apple_flow_enable_attachments`, OCR/transcription settings, phone TTS settings |
| Audit and logs | `apple_flow_log_file_path`, `apple_flow_enable_csv_audit_log`, `apple_flow_csv_audit_log_path` |

## Error Handling And Logging

- Runtime logging is written to stderr and is typically captured in `logs/apple-flow.err.log`.
- The `events` SQLite table is the canonical audit trail.
- CSV mirroring can be enabled for analytics via `apple_flow_enable_csv_audit_log`.
- Gateway health is surfaced through the Admin API and CLI health checks.
- Duplicate outbound suppression is used to reduce echo loops.

For security-specific failure modes and hardening guidance, see [SECURITY.md](../SECURITY.md).

## Performance Considerations

- Connector turns are bounded by `apple_flow_codex_turn_timeout_seconds`.
- Polling cadence is controlled per channel to avoid excessive churn.
- Helper maintenance can soft-recycle long-lived helper processes when enabled.
- Attachment extraction is guarded by size and character-count limits.
- Ambient scanning and companion behavior are opt-in so the default path stays lightweight.

## Security

Apple Flow’s main security controls are:

- sender allowlisting
- workspace restrictions
- approval gating for mutating work
- requester verification for approvals
- rate limiting
- read-only iMessage DB access
- optional Admin API bearer authentication

Use [SECURITY.md](../SECURITY.md) as the canonical threat-model and hardening reference.

## Testing

### Test strategy

The project uses `pytest` and `pytest-asyncio` for async-heavy runtime coverage. Tests focus on orchestration, approval security, routing, connectors, ingress and egress modules, gateway integrations, companion behavior, memory, scheduling, and the admin API.

### Core commands

```bash
pytest -q
pytest -v
pytest tests/test_orchestrator.py -v
pytest tests/test_admin_api.py -v
```

### Contributor expectation

For behavior changes, run `pytest -q` before considering the change complete. Add or update tests alongside connector, orchestration, gateway, or security changes.

## Contribution Notes

- Start with [CONTRIBUTING.md](../CONTRIBUTING.md) for setup, branch, commit, and PR expectations.
- Use [README.md](../README.md) for product-level overview and onboarding paths.
- Use [AGENTS.md](../AGENTS.md) when working as an AI coding agent inside this repository.
- Keep documentation updates aligned across `config.py`, `.env.example`, `README.md`, and relevant docs pages when adding new settings or commands.

## Related Documentation

- [README.md](../README.md)
- [QUICKSTART.md](./QUICKSTART.md)
- [ENV_SETUP.md](./ENV_SETUP.md)
- [AUTO_START_SETUP.md](./AUTO_START_SETUP.md)
- [BEGINNER_SETUP_10_MIN.md](./BEGINNER_SETUP_10_MIN.md)
- [AI_INSTALL_MASTER_PROMPT.md](./AI_INSTALL_MASTER_PROMPT.md)
- [SKILLS_AND_MCP.md](./SKILLS_AND_MCP.md)
- [SECURITY.md](../SECURITY.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [CHANGELOG.md](../CHANGELOG.md)

## Not Applicable To This Project

The generic documentation checklist includes some sections that are not first-class fits for Apple Flow:

- Graph database integration: not applicable.
- A single standalone public API reference for every internal class/function: only partially applicable because the project is primarily a daemon plus CLI, with the Admin API documented separately.
- A per-module changelog in this document: not applicable; the project-level changelog is maintained in [CHANGELOG.md](../CHANGELOG.md).
