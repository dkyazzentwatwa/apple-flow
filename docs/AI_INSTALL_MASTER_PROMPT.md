# AI-Led Install Master Prompt

Use this when you want an AI operator (Codex/Claude/Cline/Gemini CLI) to safely install and fully customize Apple Flow.

## How To Use

1. Clone this repo and `cd` into it.
2. Open your AI CLI.
3. Paste the prompt below.
4. Confirm each mutating action when asked.

## Master Prompt (Copy/Paste)

```text
You are my installer operator for this Apple Flow repository.

Your job: safely install, customize, validate, and verify this project end-to-end.

Operating rules:
1) Never run destructive commands.
2) Ask for explicit confirmation before every mutating action (file writes, service install/start/stop/restart, resource creation).
3) Show command output when a command fails.
4) Stop on failed validation and present remediation options.
5) Prefer project-native commands (`wizard`, `config`, `service`) over ad-hoc edits.
6) Keep a short running checklist and mark each phase done/blocked.

Workflow

Phase A - Bootstrap + Health Snapshot
1) Run:
   ./scripts/setup_autostart.sh
2) Then run:
   python -m apple_flow wizard doctor --json --env-file .env
3) Summarize:
   - health errors/warnings
   - detected connector binary
   - whether admin token is present
   - what still needs user input

Phase B - Collect Preferences (Ask Before Writes)
Collect all desired config values:
- Core:
  - apple_flow_allowed_senders (E.164, e.g. +15551234567)
  - apple_flow_allowed_workspaces
  - apple_flow_default_workspace
  - apple_flow_connector (claude-cli | codex-cli | gemini-cli | cline | kilo-cli)
  - connector command path (binary/command)
  - apple_flow_timezone (if non-default)
- Safety/policy:
  - apple_flow_require_chat_prefix
  - apple_flow_chat_prefix (if using prefix mode)
  - apple_flow_trigger_tag (default !!agent)
- Gateways:
  - enable/disable mail/reminders/notes/calendar
  - mail address allowlist if mail enabled
  - reminders list + archive list
  - notes folder + archive folder + log folder
  - calendar name
  - notes logging toggle
- Companion + memory:
  - enable companion
  - enable memory
  - memory v2 rollout flags:
    - apple_flow_enable_memory_v2
    - apple_flow_memory_v2_shadow_mode
    - apple_flow_memory_v2_migrate_on_start
- Office:
  - enable agent-office
  - soul file path
- Admin:
  - apple_flow_admin_api_token (generate strong token if missing, then show it once and warn to store securely)

Phase C - Generate Full .env Preview
1) Run one `generate-env` command using all collected wizard-supported flags, for example:
   python -m apple_flow wizard generate-env --json \
     --phone "+15551234567" \
     --workspace "/Users/me/code" \
     --connector "claude-cli" \
     --connector-command "claude" \
     --gateways "mail,reminders,notes,calendar" \
     --mail-address "me@example.com" \
     --admin-api-token "<TOKEN>" \
     --enable-agent-office \
     --soul-file "agent-office/SOUL.md" \
     --enable-notes-logging \
     --reminders-list-name "agent-task" \
     --reminders-archive-list-name "agent-archive" \
     --notes-folder-name "agent-task" \
     --notes-archive-folder-name "agent-archive" \
     --notes-log-folder-name "agent-logs" \
     --calendar-name "agent-schedule"
2) Treat `env_preview` as the full `.env` baseline.
3) Present a concise summary of key values to be written.
4) Ask for confirmation before any write.

Important connector caveat:
- `wizard generate-env` currently validates only: `claude-cli`, `codex-cli`, `gemini-cli`, `cline`.
- If user selected `kilo-cli`, generate with a supported connector first, then patch connector keys in Phase D via `config write`.

Phase D - Apply + Validate
1) After explicit confirmation, write `.env` with:
   python -m apple_flow config write --json --env-file .env --set key=value ...
2) Validate:
   python -m apple_flow config validate --json --env-file .env
3) If invalid, stop and show exact errors plus suggested fixes.
4) If user selected `kilo-cli`, set connector keys now with `config write` and re-validate.

Phase E - Ensure Gateway Resources
1) Ask confirmation before creation/update actions.
2) Run (matching chosen names/toggles):
   python -m apple_flow wizard ensure-gateways --json \
     --enable-reminders (if enabled) \
     --enable-notes (if enabled) \
     --enable-notes-logging (if enabled) \
     --enable-calendar (if enabled) \
     --reminders-list-name "..." \
     --reminders-archive-list-name "..." \
     --notes-folder-name "..." \
     --notes-archive-folder-name "..." \
     --notes-log-folder-name "..." \
     --calendar-name "..."
3) If any resource fails, stop and report exact failure details.

Phase F - Service + Runtime Verification
1) Ask confirmation before service mutation.
2) Restart:
   python -m apple_flow service restart --json
3) Verify:
   python -m apple_flow service status --json
4) If unhealthy, run:
   python -m apple_flow service logs --json --stream stderr --lines 200
5) Summarize final runtime state:
   - connector in use
   - enabled gateways + custom resource names
   - companion/memory flags (including memory v2 mode)
   - log file path

Phase G - Post-Install Functional Checks
1) Provide a short smoke-test checklist for iMessage and any enabled gateways.
2) Show a starter command set:
   - health
   - help
   - status
   - task: <something small>
3) If user wants team workflows, show:
   - system: teams list
   - system: team load <slug>
   - system: team current

Phase H - Optional Swift App (Ask First)
1) Ask whether to run the native macOS Swift onboarding/dashboard app.
2) If yes, ask confirmation before each command and run:
   ./apps/macos/AppleFlowApp/scripts/export_app.sh
   ./apps/macos/AppleFlowApp/scripts/run_standalone.sh
3) Mention optional Xcode open command:
   ./apps/macos/AppleFlowApp/scripts/open_in_xcode.sh

Completion criteria:
- Full `.env` configured (not starter-only)
- Config validation passes
- Gateway setup passes (or explicit acknowledged skips)
- Service status healthy
- User receives final summary with exact next commands
```

## Notes

- This prompt is designed for local-first, confirmation-gated setup.
- It is safe to use on existing installations; it should reconfigure without assuming a fresh install.
- The operator should preserve explicit user choices and avoid silent defaults for critical fields.
