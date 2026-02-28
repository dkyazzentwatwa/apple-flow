# Environment Configuration Reference

All Apple Flow settings are controlled via the `.env` file (or shell environment variables). Every variable uses the `apple_flow_` prefix.

**Get started:**
```bash
./scripts/setup_autostart.sh
# or manually:
# cp .env.example .env
# nano .env
```

---

## Required Settings

These must be set before the daemon will start.

| Variable | Example | Description |
|---|---|---|
| `apple_flow_allowed_senders` | `+15551234567` | Comma-separated phone numbers in E.164 format. Only messages from these numbers are processed. Your own number goes here. |
| `apple_flow_allowed_workspaces` | `/Users/yourname/code` | Comma-separated absolute paths the AI is allowed to read/write. |
| `apple_flow_default_workspace` | `/Users/yourname/code/my-project` | Default working directory for the AI connector. Must be inside `allowed_workspaces`. |
| `apple_flow_db_path` | `~/.apple-flow/relay.db` | SQLite state database path. If not explicitly set, Apple Flow auto-migrates legacy `~/.codex/relay.db` to this location when safe. |

**Phone number format:**
- Correct: `+15551234567`
- Wrong: `5551234567`, `(555) 123-4567`

---

## Connector

Pick one AI backend. The value of `apple_flow_connector` determines which is used.

| Variable | Default | Options / Description |
|---|---|---|
| `apple_flow_connector` | `codex-cli` | `codex-cli` — uses `codex exec` (requires `codex login`)<br>`claude-cli` — uses `claude -p` (requires `claude auth login`)<br>`gemini-cli` — uses `gemini -p` (requires `gemini auth login`)<br>`cline` — uses `cline -y` (supports multiple model providers) |

### Codex CLI settings (`connector=codex-cli`)

| Variable | Default | Description |
|---|---|---|
| `apple_flow_codex_cli_command` | `codex` | Path to the `codex` binary. |
| `apple_flow_codex_cli_model` | *(empty)* | Model flag passed to codex (e.g. `gpt-5.3-codex`). Empty = use codex default. |
| `apple_flow_codex_cli_context_window` | `10` | Number of recent message exchanges to inject as context per turn. |

### Claude Code CLI settings (`connector=claude-cli`)

| Variable | Default | Description |
|---|---|---|
| `apple_flow_claude_cli_command` | `claude` | Path to the `claude` binary. |
| `apple_flow_claude_cli_model` | *(empty)* | Model flag (e.g. `claude-sonnet-4-6`, `claude-opus-4-6`). Empty = claude default. |
| `apple_flow_claude_cli_context_window` | `10` | Recent exchanges to inject per turn. |
| `apple_flow_claude_cli_dangerously_skip_permissions` | `true` | Pass `--dangerously-skip-permissions` to the claude binary. |
| `apple_flow_claude_cli_tools` | *(empty)* | Comma-separated values for `--tools` (e.g. `default,WebSearch`). |
| `apple_flow_claude_cli_allowed_tools` | *(empty)* | Comma-separated values for `--allowedTools` (e.g. `WebSearch`). |

### Gemini CLI settings (`connector=gemini-cli`)

| Variable | Default | Description |
|---|---|---|
| `apple_flow_gemini_cli_command` | `gemini` | Path to the `gemini` binary. |
| `apple_flow_gemini_cli_model` | `gemini-3-flash-preview` | Model flag passed to gemini. |
| `apple_flow_gemini_cli_context_window` | `10` | Number of recent exchanges to inject per turn. |

### Cline settings (`connector=cline`)

| Variable | Default | Description |
|---|---|---|
| `apple_flow_cline_command` | `cline` | Path to the `cline` binary. |
| `apple_flow_cline_model` | *(empty)* | Model name for Cline. Empty = Cline default. |
| `apple_flow_cline_context_window` | `3` | Number of recent exchanges to inject per turn. |
| `apple_flow_cline_use_json` | `true` | Parse Cline JSON output when available. |
| `apple_flow_cline_act_mode` | `true` | Enable Cline act mode for faster execution. |

---

## Safety & Security

| Variable | Default | Description |
|---|---|---|
| `apple_flow_only_poll_allowed_senders` | `true` | Filter unknown senders at SQL query time. Keep `true` unless debugging. |
| `apple_flow_require_chat_prefix` | `false` | When `true`, only messages starting with the chat prefix (e.g. `relay:`) are processed. Natural language mode is the default (`false`). |
| `apple_flow_chat_prefix` | `relay:` | The prefix string checked when `require_chat_prefix=true`. |
| `apple_flow_approval_ttl_minutes` | `20` | How long a pending approval request stays valid before it expires. |
| `apple_flow_max_messages_per_minute` | `30` | Rate limit per sender. Messages beyond this are silently dropped. |
| `apple_flow_process_historical_on_first_start` | `false` | Skip messages already in the DB when the daemon first starts. Keep `false` to avoid a flood of old messages being replayed. |
| `apple_flow_notify_blocked_senders` | `false` | Reply to blocked senders explaining they're not allowed. Keep `false` in production. |
| `apple_flow_notify_rate_limited_senders` | `false` | Reply when rate limiting kicks in. Keep `false` in production. |

---

## Behavior & UX

| Variable | Default | Description |
|---|---|---|
| `apple_flow_send_startup_intro` | `true` | Send an iMessage intro on daemon startup with workspace + command list. |
| `apple_flow_suppress_duplicate_outbound_seconds` | `90` | Suppress identical outbound messages within this window (prevents echo loops). |
| `apple_flow_poll_interval_seconds` | `2` | How often to poll the Messages database (seconds). |
| `apple_flow_codex_turn_timeout_seconds` | `300` | Timeout for a single AI turn across all connectors (5 minutes). |
| `apple_flow_auto_context_messages` | `10` | Number of recent messages to auto-inject as context each turn. `0` disables. |
| `apple_flow_personality_prompt` | *(empty)* | System prompt injected for all chat turns. Use `{workspace}` as a placeholder. Example: `You are a senior engineer on the {workspace} project.` |
| `apple_flow_inject_tools_context` | `true` | Prepend a description of Apple Flow tools (Notes, Mail, Reminders, Calendar, iMessage) to AI prompts. |

---

## Admin API

| Variable | Default | Description |
|---|---|---|
| `apple_flow_admin_host` | `127.0.0.1` | Host for the admin API server. |
| `apple_flow_admin_port` | `8787` | Port for the admin API server. |

Access it at `http://localhost:8787` — endpoints: `/sessions`, `/approvals/pending`, `/events`, `POST /task`.

---

## Apple Mail Integration

Enable email as an additional ingress channel (optional, runs alongside iMessage).

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_mail_polling` | `false` | Enable Apple Mail as an ingress source. |
| `apple_flow_mail_allowed_senders` | *(empty)* | Comma-separated email addresses to accept. |
| `apple_flow_mail_from_address` | *(empty)* | Sender address for outbound replies. Empty = Mail.app default. |
| `apple_flow_mail_poll_account` | *(empty)* | Mail.app account name to poll. Empty = all accounts / inbox. |
| `apple_flow_mail_poll_mailbox` | `INBOX` | Mailbox to poll within the account. |
| `apple_flow_mail_max_age_days` | `2` | Only process emails received in the last N days. |
| `apple_flow_mail_signature` | `\n\n—\nApple Flow 🤖, Your 24/7 Assistant` | Signature appended to all outbound email replies. |

**Minimal config to enable:**
```bash
apple_flow_enable_mail_polling=true
apple_flow_mail_allowed_senders=you@example.com
apple_flow_mail_from_address=you@example.com
```

---

## Apple Reminders Integration

Incomplete reminders in a designated list become tasks for the AI.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_reminders_polling` | `false` | Enable Apple Reminders as a task queue. |
| `apple_flow_reminders_list_name` | `agent-task` | Reminders list to watch for new tasks. |
| `apple_flow_reminders_archive_list_name` | `agent-archive` | List to move completed reminders into. |
| `apple_flow_reminders_owner` | *(first allowed_sender)* | Sender identity used for reminder tasks (phone number). |
| `apple_flow_reminders_auto_approve` | `false` | Skip the approval gate for reminder tasks. |
| `apple_flow_reminders_poll_interval_seconds` | `5` | How often to poll Reminders (seconds). |

---

## Apple Notes Integration

Notes in a designated folder become tasks; results are appended back to the note.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_notes_polling` | `false` | Enable Apple Notes as a task ingress. |
| `apple_flow_notes_folder_name` | `agent-task` | Notes folder to watch. |
| `apple_flow_notes_archive_folder_name` | `agent-archive` | Folder to move completed notes into. |
| `apple_flow_notes_owner` | *(first allowed_sender)* | Sender identity for note tasks. |
| `apple_flow_notes_auto_approve` | `false` | Skip the approval gate for note tasks. |
| `apple_flow_notes_poll_interval_seconds` | `10` | How often to poll Notes (seconds). |
| `apple_flow_notes_fetch_timeout_seconds` | `20` | AppleScript fetch timeout per poll cycle. |
| `apple_flow_notes_fetch_retries` | `1` | Retries after a Notes fetch timeout. |
| `apple_flow_notes_fetch_retry_delay_seconds` | `1.5` | Seconds to wait between retries. |

### Notes Logging

Log every AI response as a new note (independent of notes polling).

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_notes_logging` | `false` | Create a note for each AI completion. |
| `apple_flow_notes_log_folder_name` | `agent-logs` | Folder to write log notes into (auto-created if missing). |

---

## Apple Calendar Integration

Calendar events in a designated calendar trigger tasks when they come due.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_calendar_polling` | `false` | Enable Apple Calendar as a task scheduler. |
| `apple_flow_calendar_name` | `agent-schedule` | Calendar to watch for due events. |
| `apple_flow_calendar_owner` | *(first allowed_sender)* | Sender identity for calendar tasks. |
| `apple_flow_calendar_auto_approve` | `false` | Skip the approval gate for calendar tasks. |
| `apple_flow_calendar_poll_interval_seconds` | `30` | How often to poll Calendar (seconds). |
| `apple_flow_calendar_lookahead_minutes` | `5` | How many minutes ahead to look for events becoming due. |

---

## Trigger Tag

A global tag that gates processing across all Apple app channels (Reminders, Notes, Mail, Calendar). Items without this tag are silently skipped.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_trigger_tag` | `!!agent` | Tag string required on items for them to be processed. Set to empty string `""` to process everything. |

---

## Multi-Workspace Routing

Route commands to different directories using `@alias` syntax (e.g. `task: @web-app deploy`).

| Variable | Default | Description |
|---|---|---|
| `apple_flow_workspace_aliases` | `{}` | JSON object mapping alias names to absolute workspace paths. |

**Example:**
```bash
apple_flow_workspace_aliases={"web-app":"/Users/yourname/Projects/web-app","api":"/Users/yourname/Projects/api"}
```

Then send: `task: @web-app run the test suite`

---

## Progress Streaming

Send periodic iMessage updates during long-running tasks.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_progress_streaming` | `true` | Enable intermediate milestone/progress messages. |
| `apple_flow_progress_update_interval_seconds` | `30` | Minimum seconds between progress updates. |
| `apple_flow_execution_heartbeat_seconds` | `120` | Heartbeat interval for long-running execution attempts. |
| `apple_flow_checkpoint_on_timeout` | `true` | Convert timeout outcomes into checkpoint + re-approval instead of immediate failure (until max attempts). |
| `apple_flow_max_resume_attempts` | `5` | Max execution attempts for one run before final failure. |

When a run pauses at a checkpoint, continue it with:

```bash
approve <new_request_id>
# or with additional guidance:
approve <new_request_id> <extra instructions>
```

---

## File Attachments

Allow the AI to read files sent as iMessage attachments.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_attachments` | `false` | Enable reading inbound file attachments. |
| `apple_flow_max_attachment_size_mb` | `10` | Maximum attachment size to process (MB). |
| `apple_flow_attachment_temp_dir` | `/tmp/apple_flow_attachments` | Temporary directory for attachment processing. |

---

## Agent Office

Path to the companion's personality file. Injected as companion/system context for supported stateless connectors when `enable_companion=true`.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_soul_file` | `agent-office/SOUL.md` | Path to `SOUL.md` injected into connector prompts. Relative paths are resolved from the repo root. |

Run `cd agent-office && bash setup.sh` once after cloning to scaffold the workspace directory.

---

## Companion Layer

A proactive companion loop that observes stale approvals, upcoming calendar events, overdue reminders, and office inbox items, synthesizes them with AI, and sends proactive iMessages. All companion features are disabled by default.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_companion` | `false` | Enable the CompanionLoop proactive observation loop. |
| `apple_flow_companion_poll_interval_seconds` | `300` | How often the companion checks for new observations (seconds). |
| `apple_flow_companion_max_proactive_per_hour` | `4` | Maximum proactive iMessages sent per hour (rate limit). |
| `apple_flow_companion_quiet_hours_start` | `22:00` | Start of quiet hours — no proactive messages sent during this window. |
| `apple_flow_companion_quiet_hours_end` | `07:00` | End of quiet hours. |
| `apple_flow_companion_stale_approval_minutes` | `30` | Minutes before a pending approval is flagged as stale. |
| `apple_flow_companion_calendar_lookahead_minutes` | `60` | How far ahead to look for upcoming calendar events. |
| `apple_flow_companion_enable_daily_digest` | `false` | Write a daily digest note to `agent-office/10_daily/YYYY-MM-DD.md`. |
| `apple_flow_companion_digest_time` | `08:00` | Time of day to generate the daily digest (24-hour format). |
| `apple_flow_companion_weekly_review_day` | `sunday` | Day of week for the weekly review. |
| `apple_flow_companion_weekly_review_time` | `20:00` | Time of day for the weekly review (24-hour format). |

Control the companion from iMessage:
- `system: mute` — silence all proactive messages
- `system: unmute` — re-enable proactive messages

**Minimal config to enable:**
```bash
apple_flow_enable_companion=true
```

---

## Memory

Inject durable memory from `agent-office/MEMORY.md` and topic files in `agent-office/60_memory/` into every AI prompt.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_memory` | `false` | Inject FileMemory into AI prompts before each turn. |
| `apple_flow_memory_max_context_chars` | `2000` | Maximum characters of memory content to inject per turn. Oldest entries are trimmed first. |
| `apple_flow_enable_memory_v2` | `false` | Use canonical SQLite memory retrieval for prompt injection (active mode). |
| `apple_flow_memory_v2_shadow_mode` | `false` | Compute canonical retrieval but keep legacy prompt injection; logs rollout diff metrics. |
| `apple_flow_memory_v2_migrate_on_start` | `true` | Backfill canonical memory from legacy files on daemon startup. |
| `apple_flow_memory_v2_db_path` | `` | Canonical memory DB path; empty uses `<agent-office>/.apple-flow-memory.sqlite3`. |
| `apple_flow_memory_v2_scope` | `global` | Retrieval scope selector for canonical memory entries. |
| `apple_flow_memory_v2_maintenance_interval_seconds` | `3600` | How often to run canonical memory maintenance (prune + compaction checks). |
| `apple_flow_memory_max_storage_mb` | `256` | Best-effort storage cap for canonical memory DB. |
| `apple_flow_memory_v2_include_legacy_fallback` | `true` | If canonical retrieval is empty, fall back to legacy file memory context. |

---

## Follow-Up Scheduler

Automatically schedule follow-up nudges after task completions, stored in the `scheduled_actions` SQLite table.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_follow_ups` | `false` | Enable time-triggered follow-up messages after task completions. |
| `apple_flow_default_follow_up_hours` | `2.0` | Default delay (hours) before the first follow-up is sent. |
| `apple_flow_max_follow_up_nudges` | `3` | Maximum number of follow-up messages per task before giving up. |

---

## Ambient Scanner

Passively reads Notes, Calendar, and Mail every N minutes and writes enriched summaries to memory topic files. Never sends messages.

| Variable | Default | Description |
|---|---|---|
| `apple_flow_enable_ambient_scanning` | `false` | Enable the AmbientScanner background context enrichment loop. |
| `apple_flow_ambient_scan_interval_seconds` | `900` | How often to scan for new context (seconds). Default is 15 minutes. |

---

## Recommended Safe Defaults

For production use, keep these values:

```bash
apple_flow_process_historical_on_first_start=false
apple_flow_notify_blocked_senders=false
apple_flow_notify_rate_limited_senders=false
apple_flow_only_poll_allowed_senders=true
apple_flow_require_chat_prefix=false   # natural language mode (no prefix needed)
apple_flow_chat_prefix=relay:
```

---

## Full Example `.env`

```bash
# --- Required ---
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/yourname/code
apple_flow_default_workspace=/Users/yourname/code/my-project

# --- Connector ---
apple_flow_connector=claude-cli
apple_flow_claude_cli_model=claude-sonnet-4-6
apple_flow_claude_cli_dangerously_skip_permissions=true

# --- Safety ---
apple_flow_only_poll_allowed_senders=true
apple_flow_require_chat_prefix=false
apple_flow_process_historical_on_first_start=false
apple_flow_notify_blocked_senders=false
apple_flow_notify_rate_limited_senders=false

# --- Behavior ---
apple_flow_send_startup_intro=true
apple_flow_auto_context_messages=10
apple_flow_codex_turn_timeout_seconds=300
```

See [`.env.example`](../.env.example) for a complete annotated file with every option.
