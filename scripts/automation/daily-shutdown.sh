#!/bin/bash
# daily-shutdown.sh — End-of-day shutdown reflection routine
#
# Runs daily at 18:00 to:
# - Summarize wins/blockers/carry-forward
# - Add missed capture items to inbox
# - Add memory candidates to today's note
#
# Scheduled via launchd: local.apple-flow-daily-pm.plist

set -euo pipefail

# Get script directory and source shared functions
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared-functions.sh"

# -----------------------------------------------------------------------------
# Main routine
# -----------------------------------------------------------------------------

main() {
    echo "Starting daily shutdown routine..."
    
    # Check daemon is running
    require_daemon_running
    
    # Get today's date
    local today
    today=$(get_today)
    
    # Ensure daily note exists
    ensure_daily_note
    
    # Build the prompt
    local prompt
    prompt=$(cat <<EOF'
You are running an automated end-of-day shutdown routine for the agent-office workspace.

Perform these tasks:

1. **Reflection Summary**: Review today's daily note at `10_daily/YYYY-MM-DD.md` and complete the "## End-of-Day Reflection" section with:
   - **Wins**: What went well today (2-3 items max)
   - **Blockers**: What's stuck or needs help
   - **Carry Forward**: What to roll to tomorrow

2. **Missed Captures**: Review the day's activity. If there are any items that should have been captured but weren't, add them to `00_inbox/inbox.md` now.

3. **Memory Delta Finalization**: Review today's work and add any final memory candidates to the "## Memory Delta" section. These will be promoted to `MEMORY.md` during tomorrow's morning planning.

4. **Tomorrow Prep**: Add a brief "## Tomorrow" section to today's note with the top 1-2 things to start with tomorrow morning.

5. **Log This Run**: Append a log entry to `90_logs/automation-log.md`:
   `- YYYY-MM-DD HH:MM | launchd | daily-shutdown | completed | reflection done, N memory candidates`

Keep responses concise. This is an automated routine, not a conversation.
EOF
)
    
    # Run with AI connector
    if run_with_connector "$prompt" 240; then
        log_run "daily-shutdown" "completed" "AI routine finished"
        echo "Daily shutdown completed successfully."
    else
        log_run "daily-shutdown" "failed" "AI routine returned non-zero exit code"
        echo "Daily shutdown failed." >&2
        exit 1
    fi
}

main "$@"