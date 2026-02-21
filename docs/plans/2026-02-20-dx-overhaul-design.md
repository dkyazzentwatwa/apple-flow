# DX Overhaul: Setup Wizard + Naming Cleanup

**Date:** 2026-02-20
**Status:** Approved

## Problem

The developer/user experience for setting up Apple Flow has several friction points:

1. **Stale naming**: README, CLAUDE.md, QUICKSTART.md reference "Codex Tasks", "Codex Inbox", "Codex Schedule" but actual config defaults are `agent-task`, `agent-task`, `agent-schedule`
2. **Internal `.codex/` path**: DB lives at `~/.codex/relay.db`, lock at `~/.codex/relay.daemon.lock` — confusing when Codex isn't even the default connector
3. **Manual .env editing**: Users must copy .env.example, understand 200+ lines of config, and manually fill in values
4. **Manual Apple app folder creation**: Users must manually create Reminders lists, Notes folders, and Calendar calendars before the daemon can use them
5. **No guided setup**: Non-technical users have no interactive way to configure the system

## Solution

### 1. Interactive Setup Wizard (`python -m apple_flow setup`)

A new CLI subcommand that walks users through configuration:

- Asks for phone number (with E.164 validation)
- Asks which AI connector (Claude CLI recommended, Codex CLI, Cline CLI)
- Asks which Apple app gateways to enable (multi-select)
- Asks for workspace path (what folder the AI can access)
- Auto-creates Apple app resources (Reminders list, Notes folder, Calendar) via AppleScript
- Generates .env from answers
- Checks Full Disk Access
- Offers to start the daemon

The existing `setup_autostart.sh` will create the venv + install deps, then invoke the wizard if no .env exists.

### 2. Rename `.codex/` to `.apple-flow/`

- Change `config.py` default `db_path` from `~/.codex/relay.db` to `~/.apple-flow/relay.db`
- Lock file follows automatically (`~/.apple-flow/relay.daemon.lock`)
- Update `start_beginner.sh` hardcoded lock path
- Clean break, no migration (forked repo, no existing users)

### 3. Fix All Stale Doc References

Update these files to use actual defaults (`agent-task`, `agent-schedule`):
- README.md
- CLAUDE.md
- docs/QUICKSTART.md
- AGENTS.md (if it has stale refs)
- SECURITY.md (references `~/.codex/relay.db`)

### 4. Auto-Create Apple App Resources at Daemon Startup

In `daemon.py`, before starting poll loops for enabled gateways, auto-create:
- Reminders list (if `enable_reminders_polling=true`)
- Notes folder (already exists in notes_egress.py, ensure it runs at startup too)
- Calendar (if `enable_calendar_polling=true`)

Idempotent — skips if already exists.

### 5. Clean Up .env.example

- Remove deprecated `codex_app_server_cmd` and `use_codex_cli` lines
- Make `connector=claude-cli` the uncommented default
- Remove conflicting/duplicate connector lines
- Update all comments to match reality

## Files Changed

| File | Change |
|------|--------|
| `src/apple_flow/config.py` | db_path default → `~/.apple-flow/relay.db` |
| `src/apple_flow/setup_wizard.py` | **NEW** — interactive setup wizard |
| `src/apple_flow/__main__.py` | Add `setup` subcommand |
| `src/apple_flow/daemon.py` | Auto-create Apple app resources on startup |
| `scripts/start_beginner.sh` | Update lock path, call wizard |
| `scripts/setup_autostart.sh` | Call wizard if no .env |
| `.env.example` | Clean up deprecated lines |
| `README.md` | Fix stale Codex naming |
| `CLAUDE.md` | Fix stale Codex naming |
| `docs/QUICKSTART.md` | Fix stale Codex naming |
| `SECURITY.md` | Fix `~/.codex/` reference |

## Testing

- Existing tests should pass (db_path change is just a default, tests use temp paths)
- New test: `tests/test_setup_wizard.py` — test .env generation, input validation
- Manual test: run wizard end-to-end on a clean checkout
