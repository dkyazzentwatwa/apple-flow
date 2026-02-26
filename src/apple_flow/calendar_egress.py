"""Writes AI results back to Apple Calendar event notes."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("apple_flow.calendar_egress")


class AppleCalendarEgress:
    """Updates calendar events with AI results."""

    def __init__(self, calendar_name: str = "agent-schedule"):
        self.calendar_name = calendar_name

    def annotate_event(self, event_id: str, result_text: str) -> bool:
        """Write result text into the event's description/notes.

        Returns True on success, False on failure.
        """
        escaped_cal = self.calendar_name.replace('"', '\\"')
        escaped_text = result_text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        escaped_id = event_id.replace('"', '\\"')

        script = f'''
        tell application "Calendar"
            try
                set targetCal to calendar "{escaped_cal}"
                set matchedEvent to (first event of targetCal whose uid is "{escaped_id}")
                set existingDesc to description of matchedEvent
                if existingDesc is missing value then
                    set description of matchedEvent to "[Apple Flow Result]\\n" & "{escaped_text}"
                else
                    set description of matchedEvent to existingDesc & "\\n\\n[Apple Flow Result]\\n" & "{escaped_text}"
                end if
                return "ok"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = result.stdout.strip()
            if result.returncode != 0 or output.startswith("error:"):
                logger.warning("Failed to annotate event %s: %s", event_id, output)
                return False
            logger.info("Annotated calendar event %s in %r", event_id, self.calendar_name)
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Timed out annotating event %s", event_id)
            return False
        except FileNotFoundError:
            logger.warning("osascript not found — Calendar egress requires macOS")
            return False
        except Exception as exc:
            logger.warning("Unexpected error annotating event %s: %s", event_id, exc)
            return False
