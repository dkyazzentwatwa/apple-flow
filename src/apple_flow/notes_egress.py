"""Writes Codex results back to Apple Notes.

Appends Codex response to the note body with a separator.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("apple_flow.notes_egress")


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

    def move_to_archive(
        self,
        note_id: str,
        result_text: str,
        source_folder_name: str,
        archive_subfolder_name: str,
    ) -> bool:
        """Append result to note and move to archive subfolder.

        Args:
            note_id: The x-coredata:// URI of the note
            result_text: The execution result to append
            source_folder_name: Parent folder (e.g., "codex-task")
            archive_subfolder_name: Subfolder within parent (e.g., "codex-archive")

        Returns:
            True on success, False on failure
        """
        escaped_source_folder = source_folder_name.replace('"', '\\"')
        escaped_archive_folder = archive_subfolder_name.replace('"', '\\"')
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
                set sourceFolder to folder "{escaped_source_folder}"
                set archiveFolder to folder "{escaped_archive_folder}" of folder "{escaped_source_folder}"
                set matchedNote to (first note of sourceFolder whose id is "{escaped_id}")
                set existingBody to plaintext of matchedNote
                set body of matchedNote to existingBody & "\\n\\n--- Apple Flow Result ---\\n" & "{escaped_text}"
                move matchedNote to archiveFolder
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
                    "Failed to move note %s to archive: rc=%s output=%s stderr=%s",
                    note_id,
                    result.returncode,
                    output,
                    result.stderr.strip(),
                )
                return False
            logger.info(
                "Moved note %s from %r to %r/%r",
                note_id,
                source_folder_name,
                source_folder_name,
                archive_subfolder_name,
            )
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Timed out moving note %s to archive", note_id)
            return False
        except FileNotFoundError:
            logger.warning("osascript not found — Apple Notes egress requires macOS")
            return False
        except Exception as exc:
            logger.warning("Unexpected error moving note %s to archive: %s", note_id, exc)
            return False

    def create_log_note(self, folder_name: str, title: str, body: str) -> bool:
        """Create a new plain-text note in folder_name.

        The folder is created automatically if it does not exist.
        Returns True on success, False on any failure (never raises).
        """
        def _esc(text: str) -> str:
            return (
                text
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "")
            )

        ef = _esc(folder_name)
        et = _esc(title)
        eb = _esc(body)

        script = f'''
        tell application "Notes"
            try
                if not (exists folder "{ef}") then
                    set targetFolder to make new folder with properties {{name:"{ef}"}}
                else
                    set targetFolder to folder "{ef}"
                end if
                make new note at targetFolder with properties {{name:"{et}", body:"{eb}"}}
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
                timeout=45,
            )
            output = result.stdout.strip()
            if result.returncode != 0 or output.startswith("error:"):
                logger.warning("Failed to create log note in %r: rc=%s out=%s err=%s",
                               folder_name, result.returncode, output, result.stderr.strip())
                return False
            logger.info("Created log note %r in folder %r", title[:60], folder_name)
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Timed out (45s) creating log note in %r", folder_name)
            return False
        except FileNotFoundError:
            logger.warning("osascript not found — Apple Notes egress requires macOS")
            return False
        except Exception as exc:
            logger.warning("Unexpected error creating log note in %r: %s", folder_name, exc)
            return False
