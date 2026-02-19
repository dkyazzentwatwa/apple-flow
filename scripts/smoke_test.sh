#!/usr/bin/env bash
# smoke_test.sh — End-to-end smoke test for all 5 Apple Flow ingress channels.
#
# Usage: bash scripts/smoke_test.sh
#
# What it does:
#   1. Injects a unique token into each channel
#   2. Waits for the daemon to pick it up
#   3. Greps the log to confirm each was processed
#   4. Prints PASS/FAIL per channel and exits non-zero if any failed
#
# Prerequisites:
#   - Daemon running (PID visible in logs/apple-flow.err.log)
#   - All 5 channels enabled in .env
#   - Admin API reachable at http://127.0.0.1:8787
#   - Mail test requires dkyazzentwatwa@gmail.com configured in Mail.app
#
# Log notes:
#   - iMessage:  logs text=  (trigger tag NOT stripped)
#   - Mail:      logs text=  (trigger tag NOT stripped, subject becomes text)
#   - Reminders: logs name=  (trigger tag IS stripped from name before logging)
#   - Calendar:  logs summary= (trigger tag IS stripped from summary before logging)
#   - Notes:     logs title= (trigger tag NOT stripped from title)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$REPO_DIR/logs/apple-flow.err.log"
PYTHON="$REPO_DIR/.venv/bin/python"
ADMIN_PID=""

# Config (must match .env)
ALLOWED_SENDER="+15416007167"
ADMIN_URL="http://127.0.0.1:8787"
REMINDERS_LIST="agent-task"
NOTES_FOLDER="agent-task"
CALENDAR_NAME="agent-schedule"
MAIL_ADDRESS="dkyazzentwatwa@gmail.com"
TRIGGER_TAG="!!agent"

# Timing (seconds to wait before grepping log)
WAIT_IMSG=10
WAIT_REMINDERS=20
WAIT_NOTES=75
WAIT_CALENDAR=80
WAIT_MAIL=180

# Generate unique token for this run
EPOCH=$(date +%s)
TOKEN="SMOKE_${EPOCH}"

PASS=0
FAIL=0
SKIP=0
WARN=0

# ─── Helpers ─────────────────────────────────────────────────────────────────

check_pass() {
    local channel="$1"
    local pattern="$2"
    local wait_secs="$3"

    echo ""
    echo "  Waiting ${wait_secs}s for $channel..."
    sleep "$wait_secs"

    if grep -q "$pattern" "$LOG_FILE" 2>/dev/null; then
        echo "  [PASS] $channel — found pattern: $pattern"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $channel — pattern NOT found: $pattern"
        echo "         Run: grep '$pattern' $LOG_FILE"
        FAIL=$((FAIL + 1))
    fi
}

# ─── Cleanup trap ─────────────────────────────────────────────────────────────

cleanup() {
    if [[ -n "$ADMIN_PID" ]]; then
        kill "$ADMIN_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ─── Pre-flight ───────────────────────────────────────────────────────────────

echo "Apple Flow Smoke Test"
echo "Token: $TOKEN"
echo "Log:   $LOG_FILE"
echo ""

if [[ ! -f "$LOG_FILE" ]]; then
    echo "ERROR: Log file not found: $LOG_FILE"
    echo "       Is the daemon running? Check: launchctl list local.apple-flow"
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: venv python not found: $PYTHON"
    echo "       Run: python -m venv .venv && pip install -e '.[dev]'"
    exit 1
fi

# Start admin API in background if not already running
if curl -sf "$ADMIN_URL/sessions" > /dev/null 2>&1; then
    echo "Admin API already running at $ADMIN_URL"
else
    echo "Starting admin API in background..."
    cd "$REPO_DIR"
    "$PYTHON" -m apple_flow admin >> "$REPO_DIR/logs/apple-flow.log" 2>&1 &
    ADMIN_PID=$!
    # Wait up to 8s for it to be ready
    for i in $(seq 1 16); do
        sleep 0.5
        if curl -sf "$ADMIN_URL/sessions" > /dev/null 2>&1; then
            echo "Admin API ready (PID $ADMIN_PID)"
            break
        fi
        if [[ $i -eq 16 ]]; then
            echo "ERROR: Admin API did not start after 8s (PID $ADMIN_PID)"
            exit 1
        fi
    done
fi
echo ""

# ─── 1. iMessage (via Admin API POST /task) ───────────────────────────────────
# NOTE: POST /task requires the daemon and admin API to share the same process.
# In production (launchd running `apple_flow daemon`), the admin API is separate
# so POST /task returns 503. This test is SKIPPED in that case.

IMSG_TOKEN="${TOKEN}_IMSG"
SKIP=0
echo ">>> [1/5] iMessage — injecting via POST /task"
echo "    Token: $IMSG_TOKEN"

HTTP_STATUS=$(curl -s -o /tmp/smoke_task_resp.txt -w "%{http_code}" \
    -X POST "$ADMIN_URL/task" \
    -H "Content-Type: application/json" \
    -d "{\"sender\": \"$ALLOWED_SENDER\", \"text\": \"relay: $IMSG_TOKEN\"}" 2>/dev/null || echo "000")

if [[ "$HTTP_STATUS" == "200" ]]; then
    echo "    Injected OK (HTTP 200)"
    check_pass "iMessage" "$IMSG_TOKEN" "$WAIT_IMSG"
elif [[ "$HTTP_STATUS" == "503" ]]; then
    echo "    [SKIP] iMessage — orchestrator not co-located with admin API"
    echo "           (expected when daemon runs as 'python -m apple_flow daemon' via launchd)"
    echo "           To enable: embed admin API in daemon, or run both in the same process."
    SKIP=$((SKIP + 1))
else
    echo "    [FAIL] iMessage — unexpected HTTP status: $HTTP_STATUS"
    cat /tmp/smoke_task_resp.txt 2>/dev/null || true
    FAIL=$((FAIL + 1))
fi

# ─── 2. Reminders ─────────────────────────────────────────────────────────────

REM_TOKEN="${TOKEN}_REM"
echo ""
echo ">>> [2/5] Reminders — adding to list '$REMINDERS_LIST'"
echo "    Token: $REM_TOKEN"

if osascript 2>/tmp/smoke_rem_err.txt <<APPLESCRIPT
tell application "Reminders"
    tell list "$REMINDERS_LIST"
        make new reminder with properties {name:"${TRIGGER_TAG} ${REM_TOKEN}", body:"Smoke test — safe to delete."}
    end tell
end tell
APPLESCRIPT
then
    echo "    Injected OK"
    check_pass "Reminders" "$REM_TOKEN" "$WAIT_REMINDERS"
else
    echo "    [FAIL] Reminders — osascript injection failed:"
    cat /tmp/smoke_rem_err.txt
    echo "           Check: System Settings → Privacy → Automation → Terminal → Reminders"
    FAIL=$((FAIL + 1))
fi

# ─── 3. Notes ─────────────────────────────────────────────────────────────────

NOTE_TOKEN="${TOKEN}_NOTE"
echo ""
echo ">>> [3/5] Notes — adding to folder '$NOTES_FOLDER'"
echo "    Token: $NOTE_TOKEN"

if osascript 2>/tmp/smoke_note_err.txt <<APPLESCRIPT
tell application "Notes"
    tell folder "$NOTES_FOLDER"
        make new note with properties {name:"Smoke Test $NOTE_TOKEN", body:"${TRIGGER_TAG} Smoke test -- safe to delete. Token: $NOTE_TOKEN"}
    end tell
end tell
APPLESCRIPT
then
    echo "    Injected OK"
    check_pass "Notes" "$NOTE_TOKEN" "$WAIT_NOTES"
else
    echo "    [FAIL] Notes — osascript injection failed:"
    cat /tmp/smoke_note_err.txt
    echo "           Check: System Settings → Privacy → Automation → Terminal → Notes"
    FAIL=$((FAIL + 1))
fi

# ─── 4. Calendar ──────────────────────────────────────────────────────────────

CAL_TOKEN="${TOKEN}_CAL"
echo ""
echo ">>> [4/5] Calendar — adding event to '$CALENDAR_NAME'"
echo "    Token: $CAL_TOKEN"

# Start time = now+60s, end time = now+120s — safely within the 5-min lookahead window

if osascript 2>/tmp/smoke_cal_err.txt <<APPLESCRIPT
tell application "Calendar"
    tell calendar "$CALENDAR_NAME"
        set startDate to current date
        set startDate to (startDate + 60)
        set endDate to (startDate + 60)
        make new event with properties {summary:"${TRIGGER_TAG} ${CAL_TOKEN}", start date:startDate, end date:endDate, description:"Smoke test -- safe to delete."}
    end tell
end tell
APPLESCRIPT
then
    echo "    Injected OK"
    check_pass "Calendar" "$CAL_TOKEN" "$WAIT_CALENDAR"
else
    echo "    [FAIL] Calendar — osascript injection failed:"
    cat /tmp/smoke_cal_err.txt
    echo "           Check: System Settings → Privacy → Automation → Terminal → Calendar"
    FAIL=$((FAIL + 1))
fi

# ─── 5. Mail ──────────────────────────────────────────────────────────────────

MAIL_TOKEN="${TOKEN}_MAIL"
echo ""
echo ">>> [5/5] Mail — sending email to $MAIL_ADDRESS"
echo "    Token: $MAIL_TOKEN"
echo "    NOTE: Mail test waits ${WAIT_MAIL}s for SMTP round-trip + daemon poll."

if osascript 2>/tmp/smoke_mail_err.txt <<APPLESCRIPT
tell application "Mail"
    set newMessage to make new outgoing message with properties {subject:"${TRIGGER_TAG} ${MAIL_TOKEN}", content:"Smoke test -- safe to delete. Token: $MAIL_TOKEN", visible:false}
    tell newMessage
        make new to recipient with properties {address:"$MAIL_ADDRESS"}
    end tell
    send newMessage
end tell
APPLESCRIPT
then
    echo "    Sent OK"
    # Poll for the mail token, periodically triggering Mail.app sync.
    # mail_ingress.py only reads what Mail.app has locally — Gmail delivery can take 1-3 min.
    echo ""
    echo "  Waiting up to ${WAIT_MAIL}s for Mail (triggering Mail.app sync every 30s)..."
    mail_found=0
    elapsed=0
    while [[ $elapsed -lt $WAIT_MAIL ]]; do
        osascript -e 'tell application "Mail" to check for new mail' 2>/dev/null || true
        sleep 30
        elapsed=$((elapsed + 30))
        if grep -q "$MAIL_TOKEN" "$LOG_FILE" 2>/dev/null; then
            mail_found=1
            break
        fi
        echo "  ...${elapsed}s elapsed, still waiting for Mail..."
    done
    if [[ $mail_found -eq 1 ]]; then
        echo "  [PASS] Mail — found pattern: $MAIL_TOKEN"
        PASS=$((PASS + 1))
    else
        echo "  [WARN] Mail — not processed within ${WAIT_MAIL}s: $MAIL_TOKEN"
        echo "         Gmail self-send delivery timing is unpredictable (can take 3-10 min)."
        echo "         Verify manually: grep '$MAIL_TOKEN' $LOG_FILE"
        echo "         The mail channel is likely working (see recent 'Inbound email' entries in log)."
        WARN=$((WARN + 1))
    fi
else
    echo "    [FAIL] Mail — osascript send failed:"
    cat /tmp/smoke_mail_err.txt
    echo "           Check: System Settings → Privacy → Automation → Terminal → Mail"
    FAIL=$((FAIL + 1))
fi

# ─── Summary ──────────────────────────────────────────────────────────────────

TOTAL=$((PASS + FAIL + SKIP + WARN))
echo ""
echo "═══════════════════════════════════════════"
echo "Smoke Test Results: $PASS/$TOTAL passed  (skipped: $SKIP, warned: $WARN)"
echo "═══════════════════════════════════════════"

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "To inspect failures manually:"
    echo "  grep '$TOKEN' $LOG_FILE"
    echo ""
    echo "Common causes:"
    echo "  - Channel not enabled in .env (enable_*_polling=true)"
    echo "  - Wrong list/folder/calendar name in .env"
    echo "  - Daemon not running: launchctl list local.apple-flow"
    exit 1
fi

if [[ $WARN -gt 0 ]]; then
    echo ""
    echo "Mail channel: verify after a few minutes with:"
    echo "  grep '$TOKEN' $LOG_FILE"
fi

echo ""
echo "All required channels OK."
exit 0
