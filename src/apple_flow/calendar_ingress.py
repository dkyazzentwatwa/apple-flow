"""Reads scheduled tasks from Apple Calendar via AppleScript.

Polls a designated calendar for events whose start time has arrived (within
a configurable lookahead window), converts them to InboundMessage objects,
and tracks processed event IDs in the SQLite store.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone

from .models import InboundMessage
from .protocols import StoreProtocol
from .utils import normalize_sender

logger = logging.getLogger("apple_flow.calendar_ingress")

_PROCESSED_IDS_KEY = "calendar_processed_ids"


class AppleCalendarIngress:
    """Reads events from a designated Calendar.app calendar via AppleScript."""

    def __init__(
        self,
        calendar_name: str = "agent-schedule",
        owner_sender: str = "",
        auto_approve: bool = False,
        lookahead_minutes: int = 5,
        trigger_tag: str = "",
        store: StoreProtocol | None = None,
    ):
        self.calendar_name = calendar_name
        self.owner_sender = normalize_sender(owner_sender)
        self.auto_approve = auto_approve
        self.lookahead_minutes = lookahead_minutes
        self.trigger_tag = trigger_tag.strip()
        self._store = store
        self._processed_ids: set[str] = set()
        if store is not None:
            raw = store.get_state(_PROCESSED_IDS_KEY)
            if raw:
                try:
                    self._processed_ids = set(json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    self._processed_ids = set()

    def fetch_new(
        self,
        since_rowid: int | None = None,
        limit: int = 20,
        sender_allowlist: list[str] | None = None,
        require_sender_filter: bool = False,
    ) -> list[InboundMessage]:
        raw_events = self._fetch_due_events_via_applescript(limit)
        messages: list[InboundMessage] = []

        for raw in raw_events:
            event_id = raw.get("id", "")
            if not event_id or event_id in self._processed_ids:
                continue

            summary = (raw.get("summary", "") or "").strip()
            description = (raw.get("description", "") or "").strip()
            start_date = raw.get("start_date", "")

            # Skip events that don't contain the trigger tag (if configured).
            if self.trigger_tag:
                if self.trigger_tag not in summary and self.trigger_tag not in description:
                    continue
                summary = summary.replace(self.trigger_tag, "").strip()
                description = description.replace(self.trigger_tag, "").strip()

            text = self._compose_text(summary, description)
            if not text:
                continue

            if self.auto_approve:
                prefixed_text = f"relay: {text}"
            else:
                prefixed_text = f"task: {text}"

            received_at = start_date or datetime.now(timezone.utc).isoformat()

            messages.append(
                InboundMessage(
                    id=f"cal_{event_id}",
                    sender=self.owner_sender,
                    text=prefixed_text,
                    received_at=received_at,
                    is_from_me=False,
                    context={
                        "channel": "calendar",
                        "event_id": event_id,
                        "event_summary": summary,
                        "calendar_name": self.calendar_name,
                    },
                )
            )

        return messages[:limit]

    def mark_processed(self, event_id: str) -> None:
        self._processed_ids.add(event_id)
        self._persist_processed_ids()

    def latest_rowid(self) -> int | None:
        return 0

    def _persist_processed_ids(self) -> None:
        if self._store is not None:
            self._store.set_state(_PROCESSED_IDS_KEY, json.dumps(sorted(self._processed_ids)))

    @staticmethod
    def _compose_text(summary: str, description: str) -> str:
        if not summary and not description:
            return ""
        if not description:
            return summary
        if not summary:
            return description
        return f"{summary}\n\n{description}"

    def _fetch_due_events_via_applescript(self, limit: int) -> list[dict[str, str]]:
        escaped_cal = self.calendar_name.replace('"', '\\"')

        script = f'''
        tell application "Calendar"
            set maxCount to {int(limit)}
            set resultList to {{}}
            set lookaheadMinutes to {int(self.lookahead_minutes)}

            try
                set targetCal to calendar "{escaped_cal}"
            on error
                return "[]"
            end try

            set nowDate to current date
            set futureDate to nowDate + (lookaheadMinutes * minutes)

            set dueEvents to (every event of targetCal whose start date >= (nowDate - (lookaheadMinutes * minutes)) and start date <= futureDate)

            repeat with evt in dueEvents
                if (count of resultList) >= maxCount then exit repeat

                set evtId to uid of evt as text
                set evtSummary to summary of evt as text
                try
                    set evtDescription to description of evt as text
                on error
                    set evtDescription to ""
                end try
                try
                    set evtStart to start date of evt as text
                on error
                    set evtStart to ""
                end try

                set rec to "{{\\"id\\": \\"" & my escapeJSON(evtId) & "\\", \\"summary\\": \\"" & my escapeJSON(evtSummary) & "\\", \\"description\\": \\"" & my escapeJSON(evtDescription) & "\\", \\"start_date\\": \\"" & my escapeJSON(evtStart) & "\\"}}"
                set end of resultList to rec
            end repeat

            set AppleScript's text item delimiters to ","
            return "[" & (resultList as text) & "]"
        end tell

        on escapeJSON(txt)
            set output to ""
            repeat with ch in (characters of txt)
                set charCode to (ASCII number of ch)
                if ch is "\\"" then
                    set output to output & "\\\\\\""
                else if ch is "\\\\" then
                    set output to output & "\\\\\\\\"
                else if ch is (ASCII character 10) then
                    set output to output & "\\\\n"
                else if ch is (ASCII character 13) then
                    set output to output & "\\\\n"
                else if ch is (ASCII character 9) then
                    set output to output & "\\\\t"
                else if charCode < 32 and charCode is not 10 and charCode is not 13 and charCode is not 9 then
                    set output to output & " "
                else
                    set output to output & ch
                end if
            end repeat
            return output
        end escapeJSON
        '''

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("Calendar AppleScript failed (rc=%s): %s", result.returncode, result.stderr.strip())
                return []
            output = result.stdout.strip()
            if not output or output == "[]":
                return []
            cleaned = "".join(char if (32 <= ord(char) < 127) else " " for char in output)
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Calendar AppleScript output: %s", exc)
            return []
        except subprocess.TimeoutExpired:
            logger.warning("Calendar AppleScript fetch timed out")
            return []
        except FileNotFoundError:
            logger.warning("osascript not found — Calendar ingress requires macOS")
            return []
        except Exception as exc:
            logger.warning("Unexpected error fetching calendar events: %s", exc)
            return []
