#!/bin/bash
# daily-planning.sh — Morning planning routine
#
# Runs daily at 08:30 to:
# - Ensure today's daily note exists
# - Roll forward unfinished tasks from yesterday
# - Populate Top 3 Priorities
# - Triage inbox
# - Promote memory candidates to MEMORY.md
#
# Scheduled via launchd: local.apple-flow-daily-am.plist

set -euo pipefail

# Get script directory and source shared functions
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/shared-functions.sh"

# -----------------------------------------------------------------------------
# Main routine
# -----------------------------------------------------------------------------

main() {
    echo "Starting daily planning routine..."
    
    # Check daemon is running
    require_daemon_running
    
    # Get dates
    local today yesterday
    today=$(get_today)
    yesterday=$(get_yesterday)
    
    # Ensure daily note exists
    ensure_daily_note
    
    # Build the prompt
    local prompt
    prompt=$(cat <<EOF'
You are running an automated morning planning routine for the agent-office workspace.

Perform these tasks:

1. **Daily Note Setup**: Ensure today's daily note exists at `10_daily/YYYY-MM-DD.md`. If missing, create it from the template at `templates/daily-note.md`.

2. **Roll Forward Tasks**: Check yesterday's daily note (`10_daily/EOF
cat <<EOF
${yesterday}.mdEOF
cat <<EOF'
) for any unfinished tasks in "Open Loops" or unchecked items. Copy them to today's "Open Loops" section.

3. **Top 3 Priorities**: Review `20_projects/` for active work and populate today's "Top 3 Priorities" section with the most important items to focus on today.

4. **Inbox Triage**: Review `00_inbox/inbox.md` and categorize items:
   - **Keep**: Leave in inbox (reference items, someday items)
   - **Do**: Move to today's daily note under a new "## From Inbox" section
   - **Delegate**: Note the owner and due date, move to "## Delegated" section
   - **Archive**: Move to `50_archive/inbox-archive.md` with a timestamp
   
   Update the inbox file after triage.

5. **Memory Consolidation**: Review yesterday's "Memory Delta" section. Promote validated, durable items to `MEMORY.md`. Remove them from yesterday's delta after promoting.

6. **Log This Run**: Append a log entry to `90_logs/automation-log.md`:
   `- YYYY-MM-DD HH:MM | launchd | daily-planning | completed | N priorities set, M inbox triaged`

Keep responses concise. This is an automated routine, not a conversation.
EOF
)
    
    # Run with AI connector
    if run_with_connector "$prompt" 300; then
        log_run "daily-planning" "completed" "AI routine finished"
        echo "Daily planning completed successfully."
    else
        log_run "daily-planning" "failed" "AI routine returned non-zero exit code"
        echo "Daily planning failed." >&2
        exit 1
    fi
}

main "$@"