"""Writes AI results back to Apple Reminders and marks them complete.

Unlike iMessage/Mail egress which sends new messages, this egress *mutates*
the source reminder: it writes the AI response into the reminder's notes
field and marks it as completed.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("apple_flow.reminders_egress")
REMINDERS_APP_TARGET = 'application id "com.apple.reminders"'


class AppleRemindersEgress:
    """Updates reminders in Reminders.app with AI results."""

    def __init__(self, list_name: str = "agent-task"):
        self.list_name = list_name

    def _resolve_list_selector(self, selector: str) -> dict[str, str] | None:
        from . import apple_tools

        resolved = apple_tools.reminders_resolve_list_selector(selector)
        if resolved is None:
            logger.warning("Unable to resolve Reminders selector %r", selector)
            return None
        return {
            "id": str(resolved.get("id", "")),
            "name": str(resolved.get("name", "")),
            "path": str(resolved.get("path", "")),
            "source": str(resolved.get("source", "")),
        }

    def complete_reminder(self, reminder_id: str, result_text: str) -> bool:
        """Write ``result_text`` into the reminder's notes and mark it complete.

        Returns True on success, False on failure.
        """
        resolved_list = self._resolve_list_selector(self.list_name)
        if resolved_list is None:
            return False
        if resolved_list.get("id"):
            escaped_list_id = resolved_list["id"].replace('"', '\\"')
            target_list_clause = f'set taskList to first list whose id is "{escaped_list_id}"'
        else:
            escaped_list_name = resolved_list["name"].replace('"', '\\"')
            target_list_clause = f'set taskList to list "{escaped_list_name}"'
        escaped_text = (
            result_text
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )
        escaped_id = reminder_id.replace('"', '\\"')

        script = f'''
        tell {REMINDERS_APP_TARGET}
            try
                {target_list_clause}
                set matchedReminder to (first reminder of taskList whose id is "{escaped_id}")
                set body of matchedReminder to "{escaped_text}"
                set completed of matchedReminder to true
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
                logger.warning(
                    "Failed to complete reminder %s: rc=%s output=%s stderr=%s",
                    reminder_id,
                    result.returncode,
                    output,
                    result.stderr.strip(),
                )
                return False
            logger.info("Completed reminder %s in list %r", reminder_id, self.list_name)
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Timed out completing reminder %s", reminder_id)
            return False
        except FileNotFoundError:
            logger.warning("osascript not found — Apple Reminders egress requires macOS")
            return False
        except Exception as exc:
            logger.warning("Unexpected error completing reminder %s: %s", reminder_id, exc)
            return False

    def annotate_reminder(self, reminder_id: str, note: str) -> bool:
        """Append a note to the reminder's body without completing it.

        Useful for writing the plan while awaiting approval.
        """
        resolved_list = self._resolve_list_selector(self.list_name)
        if resolved_list is None:
            return False
        if resolved_list.get("id"):
            escaped_list_id = resolved_list["id"].replace('"', '\\"')
            target_list_clause = f'set taskList to first list whose id is "{escaped_list_id}"'
        else:
            escaped_list_name = resolved_list["name"].replace('"', '\\"')
            target_list_clause = f'set taskList to list "{escaped_list_name}"'
        escaped_note = (
            note
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )
        escaped_id = reminder_id.replace('"', '\\"')

        script = f'''
        tell {REMINDERS_APP_TARGET}
            try
                {target_list_clause}
                set matchedReminder to (first reminder of taskList whose id is "{escaped_id}")
                set existingBody to body of matchedReminder
                if existingBody is missing value then
                    set body of matchedReminder to "{escaped_note}"
                else
                    set body of matchedReminder to existingBody & "\\n\\n" & "{escaped_note}"
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
                logger.warning(
                    "Failed to annotate reminder %s: rc=%s output=%s",
                    reminder_id,
                    result.returncode,
                    output,
                )
                return False
            return True
        except Exception as exc:
            logger.warning("Unexpected error annotating reminder %s: %s", reminder_id, exc)
            return False

    def move_to_archive(
        self,
        reminder_id: str,
        result_text: str,
        source_list_name: str,
        archive_list_name: str,
    ) -> bool:
        """Move reminder to archive list, write result to notes, and mark complete.

        Args:
            reminder_id: The x-apple-reminder:// URI of the reminder
            result_text: The AI execution result to write to the reminder body
            source_list_name: The list where the reminder currently lives
            archive_list_name: The list to move the reminder to

        Returns:
            True on success, False on failure
        """
        resolved_source_list = self._resolve_list_selector(source_list_name)
        resolved_archive_list = self._resolve_list_selector(archive_list_name)
        if resolved_source_list is None or resolved_archive_list is None:
            return False
        if resolved_source_list.get("id"):
            escaped_source_id = resolved_source_list["id"].replace('"', '\\"')
            source_list_clause = f'set sourceList to first list whose id is "{escaped_source_id}"'
        else:
            escaped_source_name = resolved_source_list["name"].replace('"', '\\"')
            source_list_clause = f'set sourceList to list "{escaped_source_name}"'
        if resolved_archive_list.get("id"):
            escaped_archive_id = resolved_archive_list["id"].replace('"', '\\"')
            archive_list_clause = f'set archiveList to first list whose id is "{escaped_archive_id}"'
        else:
            escaped_archive_name = resolved_archive_list["name"].replace('"', '\\"')
            archive_list_clause = f'set archiveList to list "{escaped_archive_name}"'
        escaped_text = (
            result_text
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )
        escaped_id = reminder_id.replace('"', '\\"')

        script = f'''
        tell {REMINDERS_APP_TARGET}
            try
                {source_list_clause}
                {archive_list_clause}
                set matchedReminder to (first reminder of sourceList whose id is "{escaped_id}")
                set body of matchedReminder to "{escaped_text}"
                set completed of matchedReminder to true
                move matchedReminder to archiveList
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
                logger.warning(
                    "Failed to move reminder %s to archive: rc=%s output=%s stderr=%s",
                    reminder_id,
                    result.returncode,
                    output,
                    result.stderr.strip(),
                )
                return False
            logger.info(
                "Moved reminder %s from %r to %r and marked complete",
                reminder_id,
                source_list_name,
                archive_list_name,
            )
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Timed out moving reminder %s to archive", reminder_id)
            return False
        except FileNotFoundError:
            logger.warning("osascript not found — Apple Reminders egress requires macOS")
            return False
        except Exception as exc:
            logger.warning("Unexpected error moving reminder %s to archive: %s", reminder_id, exc)
            return False
