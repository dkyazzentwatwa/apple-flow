# Implementation Plan: 8 New Intelligent Features for Codex Relay

## Implementation Order (dependency-aware)

Features are ordered so earlier ones provide foundations for later ones.

---

## Feature 1: Multi-Workspace Routing (#4 from brainstorm)

**Goal:** Parse `@workspace-alias` from command text to route tasks to different repos.

### Files to modify:
- `src/codex_relay/config.py` — Add `workspace_aliases: dict[str, str]` config field (e.g. `{"web-app": "/Users/cypher/code/web-app"}`)
- `.env.example` — Add `codex_relay_workspace_aliases` example
- `src/codex_relay/commanding.py` — Extract `@alias` from command text, add `workspace` field to `ParsedCommand`
- `src/codex_relay/orchestrator.py` — Use parsed workspace alias to resolve target workspace instead of always using `default_workspace`. Pass resolved workspace to `_handle_approval_required_command()` and `_build_non_mutating_prompt()`
- `tests/test_command_parser.py` — Tests for `@alias` extraction
- `tests/test_workspace_routing.py` — New: end-to-end routing tests with FakeStore/FakeConnector

### Design:
- Syntax: `task: @web-app fix the CSS grid` or `relay: @api-server what's in src/`
- `parse_command()` strips `@alias` from payload, returns it in `ParsedCommand.workspace`
- Orchestrator resolves alias → absolute path, validates against `allowed_workspaces`
- Falls back to `default_workspace` if no alias given

---

## Feature 2: Health Dashboard (#10 from brainstorm)

**Goal:** `health:` command returns daemon stats via iMessage.

### Files to modify:
- `src/codex_relay/commanding.py` — Add `CommandKind.HEALTH` enum value, parse `health:` and `health` prefix
- `src/codex_relay/orchestrator.py` — Add health handler that queries store for stats (doesn't hit connector)
- `src/codex_relay/store.py` — Add `get_stats()` method: count sessions, messages, runs by state, pending approvals, recent events
- `tests/test_health_dashboard.py` — New: health command parsing, stats generation, response formatting

### Design:
- Non-mutating command, no connector call needed
- Queries store for: active sessions count, messages processed today, runs by state, pending approvals, last error event, uptime (stored as kv_state at daemon start)
- Daemon sets `kv_state["daemon_started_at"]` on boot
- Response formatted as a clean text summary

---

## Feature 3: Conversation Memory / Context Carry-Over (#6 from brainstorm)

**Goal:** `history:` command queries past interactions. Auto-inject relevant context into prompts.

### Files to modify:
- `src/codex_relay/commanding.py` — Add `CommandKind.HISTORY` enum value, parse `history:` prefix
- `src/codex_relay/store.py` — Add `search_messages(sender, query, limit)` method that searches message text with LIKE. Add `recent_messages(sender, limit)` for fetching recent history.
- `src/codex_relay/orchestrator.py` — Add history handler that queries store and returns summary. For non-history commands, optionally inject recent context snippet from store into prompts.
- `tests/test_conversation_memory.py` — New: history search, context injection, edge cases

### Design:
- `history:` with no args → last 10 messages from this sender
- `history: auth` → search messages from this sender containing "auth"
- Auto-context: orchestrator prepends last N relevant exchanges to prompts (configurable via `codex_relay_auto_context_messages: int = 0`, 0 = disabled)
- Leverages existing `messages` table — no schema changes needed, just new queries

---

## Feature 4: Siri Shortcuts / Shortcuts.app Bridge (#1 from brainstorm)

**Goal:** POST endpoint on admin API to submit tasks programmatically (enables Shortcuts.app / curl).

### Files to modify:
- `src/codex_relay/main.py` — Add `POST /task` endpoint that accepts `{sender, text}`, creates InboundMessage, calls orchestrator.handle_message(), returns result
- `src/codex_relay/daemon.py` — Pass orchestrator reference to FastAPI app state so the endpoint can use it. Start admin server alongside polling loops.
- `tests/test_admin_api.py` — Add tests for POST /task endpoint with various command types

### Design:
- Endpoint: `POST /task` with body `{"sender": "+15551234567", "text": "relay: explain the auth module"}`
- Validates sender against allowlist (reuses PolicyEngine)
- Calls `orchestrator.handle_message()` synchronously
- Returns `{"kind": "chat", "response": "...", "run_id": null, "approval_request_id": null}`
- Shortcuts.app action: "Get Contents of URL" → POST to `http://localhost:8787/task`
- Also useful for curl/scripts/automation

---

## Feature 5: Notes.app as Long-Form Workspace (#2 from brainstorm)

**Goal:** Poll a designated Notes folder for new/updated notes as long-form task briefs.

### Files to create:
- `src/codex_relay/notes_ingress.py` — AppleScript to poll Notes.app for notes in a designated folder
- `src/codex_relay/notes_egress.py` — AppleScript to append Codex results back to the note
- `tests/test_notes_ingress.py` — Ingress tests (monkeypatched AppleScript)
- `tests/test_notes_egress.py` — Egress tests

### Files to modify:
- `src/codex_relay/config.py` — Add notes config: `enable_notes_polling`, `notes_folder_name`, `notes_owner`, `notes_auto_approve`, `notes_poll_interval_seconds`
- `.env.example` — Add notes config examples
- `src/codex_relay/daemon.py` — Add `_poll_notes_loop()` alongside other channels
- `CLAUDE.md` — Document notes integration

### Design:
- Designated folder in Notes.app (default: "Codex Inbox")
- Ingress polls for notes modified since last check (track modification dates in store)
- Note title = task summary, note body = detailed spec/brief
- If title starts with a command prefix (`task:`, `idea:`, etc.), use that; otherwise default to `relay:`
- Results appended to the bottom of the same note with a separator (`--- Codex Response ---`)
- Processed note IDs tracked in store (like reminders)
- Hybrid egress: conversations via iMessage, results written back to note

---

## Feature 6: Calendar-Driven Scheduled Tasks (#3 from brainstorm)

**Goal:** Calendar events in a designated calendar trigger time-based Codex work.

### Files to create:
- `src/codex_relay/calendar_ingress.py` — AppleScript to poll Calendar.app for events in a designated calendar whose start time has arrived
- `src/codex_relay/calendar_egress.py` — AppleScript to write results into event notes
- `tests/test_calendar_ingress.py` — Ingress tests
- `tests/test_calendar_egress.py` — Egress tests

### Files to modify:
- `src/codex_relay/config.py` — Add calendar config: `enable_calendar_polling`, `calendar_name`, `calendar_owner`, `calendar_auto_approve`, `calendar_poll_interval_seconds`, `calendar_lookahead_minutes`
- `.env.example` — Add calendar config examples
- `src/codex_relay/daemon.py` — Add `_poll_calendar_loop()`
- `CLAUDE.md` — Document calendar integration

### Design:
- Designated calendar (default: "Codex Schedule")
- Polls for events whose start time is within `lookahead_minutes` (default: 5) of now
- Event title = task description, event notes = additional context/details
- Only fires once per event (tracked by event ID in store)
- Results written to event notes field after execution
- Event NOT deleted — left for user's reference with results appended
- Supports recurring events: each occurrence gets its own processed-ID entry
- Useful for: nightly test runs, periodic audits, scheduled deployments

---

## Feature 7: Progress Streaming for Long Tasks (#5 from brainstorm)

**Goal:** Send incremental progress updates via iMessage during long-running task/project executions.

### Files to modify:
- `src/codex_relay/codex_cli_connector.py` — Add `run_turn_streaming(thread_id, prompt, on_progress)` method that reads stdout line-by-line and calls a callback
- `src/codex_relay/orchestrator.py` — In `_resolve_approval()` (executor phase), use streaming connector to send periodic progress updates via egress
- `src/codex_relay/config.py` — Add `progress_update_interval_seconds: float = 30.0` (minimum interval between progress messages), `enable_progress_streaming: bool = False`
- `tests/test_progress_streaming.py` — New: streaming callback tests, interval throttling

### Design:
- Only applies to `task:` and `project:` commands during the executor phase (after approval)
- CLI connector spawns subprocess and reads stdout incrementally (not `capture_output=True`)
- Every `progress_update_interval_seconds`, sends a throttled update: `"[Progress] Step N: <last meaningful line>"`
- Egress dedup window is respected (won't spam identical updates)
- If connector doesn't support streaming, falls back to current blocking behavior
- Final response still sent in full as before

---

## Feature 8: File Attachments In/Out (#8 from brainstorm)

**Goal:** Process inbound image/file attachments, send file outputs back.

### Files to modify:
- `src/codex_relay/ingress.py` — Extend SQL query to JOIN `attachment` table from chat.db. Add attachment paths to InboundMessage context.
- `src/codex_relay/models.py` — Ensure `context` dict can carry `attachments: list[dict]` with path/mime/filename
- `src/codex_relay/orchestrator.py` — When attachments present, include file references in prompt. For images: note that Codex is multimodal and can process them. For code files: read and inline content.
- `src/codex_relay/egress.py` — Add method to send iMessage with file attachment via AppleScript (`set theAttachment to POSIX file "/path/to/file"`)
- `src/codex_relay/config.py` — Add `enable_attachments: bool = False`, `max_attachment_size_mb: int = 10`, `attachment_temp_dir: str = "/tmp/codex_relay_attachments"`
- `tests/test_attachments.py` — New: attachment extraction from chat.db schema, prompt building with attachments, egress attachment sending

### Design:
- **Inbound:** chat.db has `message_attachment_join` and `attachment` tables. Query attachment paths for each message. Copy to temp dir for processing.
- **Prompt enhancement:** For images, add `[Attached image: /path/to/image.png]` to prompt. For text/code files, inline contents. For other types, note filename and type.
- **Outbound:** When Codex response references a generated file (detected by path pattern in workspace), send as iMessage attachment using AppleScript POSIX file.
- **Size limits:** Skip attachments over configured max size. Log warning.
- **Temp cleanup:** Clean attachment temp dir on daemon shutdown.

---

## Summary: File Change Matrix

| File | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 |
|------|----|----|----|----|----|----|----|----|
| `config.py` | M | | M | | M | M | M | M |
| `.env.example` | M | | | | M | M | | M |
| `commanding.py` | M | M | M | | | | | |
| `orchestrator.py` | M | M | M | | | | M | M |
| `store.py` | | M | M | | | | | |
| `main.py` | | | | M | | | | |
| `daemon.py` | | M | | M | M | M | | |
| `models.py` | | | | | | | | M |
| `ingress.py` | | | | | | | | M |
| `egress.py` | | | | | | | | M |
| `codex_cli_connector.py` | | | | | | | M | |
| `CLAUDE.md` | M | M | M | M | M | M | M | M |
| **New files** | 1 test | 1 test | 1 test | 0 | 2+2 tests | 2+2 tests | 1 test | 1 test |

M = Modified, Numbers = new files created

## Total estimated new/modified files: ~35 files
## Total estimated new tests: ~8 test files with ~100+ test cases
