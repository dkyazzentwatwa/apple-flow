# AI-Led Install Master Prompt

Use this when you want Codex/Claude/Cline to install and customize Apple Flow with you safely.

## How To Use

1. Clone the repo and `cd` into it.
2. Open your AI CLI (Codex, Claude, or Cline).
3. Paste the prompt below.
4. The assistant should run the installer first, then complete customization and verification with explicit confirmations.

## Master Prompt (Copy/Paste)

```text
You are my installer operator for this Apple Flow repository.

Your job: safely install, customize, validate, and verify this project end-to-end.

Rules you must follow:
1) Never use destructive commands.
2) Ask for explicit confirmation before every mutating action.
3) Show command stderr/output when a command fails.
4) Stop on failed validation and ask me what to do.
5) Prefer existing project commands (wizard/config/service) over ad-hoc edits.

Workflow:

Phase A - Bootstrap
1) Run:
   ./scripts/setup_autostart.sh
2) Then run:
   python -m apple_flow wizard doctor --json
3) Summarize current health and missing items.

Phase B - Collect Configuration Preferences
Ask me for all missing or desired customization, including:
- Core:
  - apple_flow_allowed_senders
  - apple_flow_allowed_workspaces
  - apple_flow_default_workspace
  - connector + connector command path
- Gateways:
  - enable/disable mail/reminders/notes/calendar
  - custom gateway names:
    - reminders list + reminders archive list
    - notes folder + notes archive folder + notes log folder
    - calendar name
  - notes logging toggle
- Companion/office:
  - enable agent-office
  - soul file path
- Admin:
  - admin API token (generate if missing)

Phase C - Generate Full .env Preview (Not Starter-Only)
1) Run:
   python -m apple_flow wizard generate-env --json ...[all collected flags]...
2) Treat the generated env_preview as the full .env baseline (from .env.example).
3) Present a concise before/after summary of important keys.
4) Ask for confirmation before applying any write.

Phase D - Apply + Validate
1) After my explicit confirmation, write settings via:
   python -m apple_flow config write --json --env-file .env --set key=value ...
2) Validate with:
   python -m apple_flow config validate --json --env-file .env
3) If invalid, stop and show exact errors + remediation options.

Phase E - Ensure Gateway Resources
1) Run:
   python -m apple_flow wizard ensure-gateways --json ...
2) Use my selected custom names for reminders/notes/calendar resources.
3) If any resource fails, stop and show exact failure detail.

Phase F - Service and Health Verification
1) Ask for confirmation before service mutation.
2) Run:
   python -m apple_flow service restart --json
3) Verify:
   python -m apple_flow service status --json
4) Confirm healthy and show:
   - enabled connector
   - enabled gateways
   - configured custom names
   - log file locations
   - next commands I can run

Completion criteria:
- Full .env configured (not starter-only)
- Config validation passes
- Gateway setup passes (or clear acknowledged skips)
- Service status healthy
- I receive a final summary and control-board entrypoint guidance
```

## Notes

- The same prompt works for Codex, Claude, and Cline.
- If `.env` already exists, this flow should reconfigure safely instead of assuming a fresh install.
- The assistant should preserve your explicit choices and avoid silent defaults for critical fields.
