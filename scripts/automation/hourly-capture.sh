#!/bin/bash
# hourly-capture.sh — Hourly capture + triage routine
#
# Runs every hour at :05 to:
# - Append capture entries to inbox
# - Ensure daily note exists
# - Update work log
# - Add memory candidates
#
# Scheduled via launchd: local.apple-flow-hourly.plist

set -euo pipefail

# Get script directory and source shared functions
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared-functions.sh"

# -----------------------------------------------------------------------------
# Main routine
# -----------------------------------------------------------------------------

main() {
    echo "Starting hourly capture routine..."
    
    # Check daemon is running
    require_daemon_running
    
    # Ensure daily note exists before AI runs
    ensure_daily_note
    
    # Build the prompt
    local prompt
    prompt=$(cat <<'EOF'
You are running an automated hourly capture routine for the agent-office workspace.

Perform these tasks:

1. **Inbox Capture**: Review recent activity and append any new capture entries to `00_inbox/inbox.md`. Use format:
   `- [ ] YYYY-MM-DD HH:MM | source | note`
   Only add genuinely new items, don't duplicate existing ones.

2. **Daily Note Check**: Verify today's daily note exists at `10_daily/YYYY-MM-DD.md`. If not, create it from the template.

3. **Work Log Update**: Append a short status block to today's `## Work Log` section summarizing what happened in the last hour. Keep it brief.

4. **Memory Candidates**: If you noticed anything worth remembering long-term, add it to today's `## Memory Delta` section.

5. **Log This Run**: Append a log entry to `90_logs/automation-log.md`:
   `- YYYY-MM-DD HH:MM | launchd | hourly-capture | completed | N inbox items, M memory candidates`

Keep responses concise. This is an automated routine, not a conversation.
EOF
)
    
    # Run with AI connector
    if run_with_connector "$prompt" 180; then
        log_run "hourly-capture" "completed" "AI routine finished"
        echo "Hourly capture completed successfully."
    else
        log_run "hourly-capture" "failed" "AI routine returned non-zero exit code"
        echo "Hourly capture failed." >&2
        exit 1
    fi
}

main "$@"