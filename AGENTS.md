# AGENTS.md

## Project
Apple Flow is a local-first macOS daemon that bridges iMessage, Apple Mail, Apple Reminders, Apple Notes, and Apple Calendar to Codex CLI. It uses stateless `codex exec` by default to avoid state corruption.

Core goals:
- Read inbound messages/tasks from iMessage, Mail, Reminders, Notes, and Calendar.
- Route allowlisted senders into Codex CLI via `codex exec`.
- Enforce safe execution with approval gates for mutating operations.
- Send replies back via AppleScript across all channels.

## Working Rules

### 1) Safety first
- Never disable sender allowlist by default.
- Keep `apple_flow_only_poll_allowed_senders=true`.
- Keep `apple_flow_require_chat_prefix=true` unless explicitly requested.
- Keep mutating workflows behind approval (`task:` / `project:`).

### 2) Startup behavior
- Use `./scripts/start_beginner.sh` for normal runs.
- The daemon is foreground and should stay running.
- If startup seems idle, check for:
  - Full Disk Access for terminal app
  - valid `apple_flow_messages_db_path`
  - valid `codex login`

### 3) Avoid iMessage loops
- Respect duplicate outbound suppression settings.
- Do not remove echo suppression without explicit user request.
- Prefer prefix-triggered general chat (`relay:`) for self-chat testing.

### 4) Config hygiene
- Keep `.env.example` aligned with runtime settings in `src/apple_flow/config.py`.
- New config fields must have:
  - sensible defaults
  - docs in `README.md`
  - sample in `.env.example`

### 5) Logging expectations
- Terminal logs should clearly show:
  - inbound row processed or ignored
  - ignore reason (echo/prefix/empty/etc.)
  - handled command kind and duration
- Avoid noisy spam logs; prefer actionable logs.

## Development Workflow

### Before changes
1. Reproduce the issue with current startup flow.
2. Identify root cause before patching.

### During changes
1. Keep patches minimal and focused.
2. Update tests for behavior changes.

### After changes
Run:
```bash
source .venv/bin/activate
pytest -q
```

Expected: all tests passing.

## Key Files
- Runtime config: `src/apple_flow/config.py`
- Main loop: `src/apple_flow/daemon.py`
- iMessage ingress/egress: `src/apple_flow/ingress.py`, `src/apple_flow/egress.py`
- Mail ingress/egress: `src/apple_flow/mail_ingress.py`, `src/apple_flow/mail_egress.py`
- Reminders ingress/egress: `src/apple_flow/reminders_ingress.py`, `src/apple_flow/reminders_egress.py`
- Notes ingress/egress: `src/apple_flow/notes_ingress.py`, `src/apple_flow/notes_egress.py`
- Calendar ingress/egress: `src/apple_flow/calendar_ingress.py`, `src/apple_flow/calendar_egress.py`
- CLI connector: `src/apple_flow/codex_cli_connector.py`
- Orchestration: `src/apple_flow/orchestrator.py`
- Startup script: `scripts/start_beginner.sh`
- Docs: `README.md`, `docs/QUICKSTART.md`

## User Experience Priorities
- Beginner-first defaults.
- Clear, explicit startup and error messages.
- Safe by default over clever by default.
- Fast feedback in terminal for every received/ignored/handled message.


## Skills
A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill.
### Available skills
- skill-creator: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowledge, workflows, or tool integrations. (file: /Users/cypher-server/.codex/skills/.system/skill-creator/SKILL.md)
- skill-installer: Install Codex skills into $CODEX_HOME/skills from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos). (file: /Users/cypher-server/.codex/skills/.system/skill-installer/SKILL.md)
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
