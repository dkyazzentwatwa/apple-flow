"""Writes Codex results back to Apple Notes.

Appends Codex response to the note body with a separator.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("codex_relay.notes_egress")


class AppleNotesEgress:
    """Updates notes in Notes.app with Codex results."""

    def __init__(self, folder_name: str = "Codex Inbox"):
        self.folder_name = folder_name

    def append_result(self, note_id: str, result_text: str) -> bool:
        """Append Codex result to the note body with a separator.

        Returns True on success, False on failure.
        """
        escaped_folder = self.folder_name.replace('"', '\\"')
        escaped_text = (
            result_text
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )
        escaped_id = note_id.replace('"', '\\"')

        script = f'''
        tell application "Notes"
            try
                set targetFolder to folder "{escaped_folder}"
                set matchedNote to (first note of targetFolder whose id is "{escaped_id}")
                set existingBody to plaintext of matchedNote
                set body of matchedNote to existingBody & "\\n\\n--- Codex Response ---\\n" & "{escaped_text}"
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
                logger.warning("Failed to update note %s: %s", note_id, output)
                return False
            logger.info("Updated note %s in folder %r", note_id, self.folder_name)
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Timed out updating note %s", note_id)
            return False
        except FileNotFoundError:
            logger.warning("osascript not found — Apple Notes egress requires macOS")
            return False
        except Exception as exc:
            logger.warning("Unexpected error updating note %s: %s", note_id, exc)
            return False
