"""Reads inbound tasks from Apple Notes via AppleScript.

Polls a designated Notes folder for notes, converts them to InboundMessage
objects, and tracks processed note IDs in the SQLite store.  Each note becomes
a command for Codex (title may contain a prefix like ``task:``).
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone

from .models import InboundMessage
from .protocols import StoreProtocol

logger = logging.getLogger("apple_flow.notes_ingress")

_PROCESSED_IDS_KEY = "notes_processed_ids"


class AppleNotesIngress:
    """Reads notes from a designated Notes.app folder via AppleScript."""

    def __init__(
        self,
        folder_name: str = "Codex Inbox",
        trigger_tag: str = "#codex",
        owner_sender: str = "",
        auto_approve: bool = False,
        store: StoreProtocol | None = None,
    ):
        self.folder_name = folder_name
        self.trigger_tag = trigger_tag.strip()
        self.owner_sender = owner_sender
        self.auto_approve = auto_approve
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
        raw_notes = self._fetch_notes_via_applescript(limit)
        messages: list[InboundMessage] = []

        for raw in raw_notes:
            note_id = raw.get("id", "")
            if not note_id or note_id in self._processed_ids:
                continue

            title = (raw.get("name", "") or "").strip()
            body = (raw.get("body", "") or "").strip()
            mod_date = raw.get("modification_date", "")

            # Only process notes that contain the trigger tag
            if self.trigger_tag and self.trigger_tag not in body and self.trigger_tag not in title:
                continue

            text = self._compose_text(title, body)
            if not text:
                continue

            # Use command prefix from title if present, otherwise default.
            if not self._has_command_prefix(title):
                if self.auto_approve:
                    text = f"relay: {text}"
                else:
                    text = f"task: {text}"

            received_at = mod_date or datetime.now(timezone.utc).isoformat()

            messages.append(
                InboundMessage(
                    id=f"note_{note_id}",
                    sender=self.owner_sender,
                    text=text,
                    received_at=received_at,
                    is_from_me=False,
                    context={
                        "channel": "notes",
                        "note_id": note_id,
                        "note_title": title,
                        "folder_name": self.folder_name,
                    },
                )
            )

        return messages[:limit]

    def mark_processed(self, note_id: str) -> None:
        self._processed_ids.add(note_id)
        self._persist_processed_ids()

    def latest_rowid(self) -> int | None:
        return 0

    def _persist_processed_ids(self) -> None:
        if self._store is not None:
            self._store.set_state(_PROCESSED_IDS_KEY, json.dumps(sorted(self._processed_ids)))

    @staticmethod
    def _has_command_prefix(title: str) -> bool:
        lowered = title.lower()
        for prefix in ("relay:", "task:", "project:", "idea:", "plan:"):
            if lowered.startswith(prefix):
                return True
        return False

    @staticmethod
    def _compose_text(title: str, body: str) -> str:
        if not title and not body:
            return ""
        if not body:
            return title
        if not title:
            return body
        return f"{title}\n\n{body}"

    def _fetch_notes_via_applescript(self, limit: int) -> list[dict[str, str]]:
        escaped_folder = self.folder_name.replace('"', '\\"')

        script = f'''
        tell application "Notes"
            set maxCount to {int(limit)}
            set resultList to {{}}

            try
                set targetFolder to folder "{escaped_folder}"
            on error
                return "[]"
            end try

            set allNotes to every note of targetFolder

            repeat with n in allNotes
                if (count of resultList) >= maxCount then exit repeat

                set nId to id of n as text
                set nName to name of n as text
                try
                    set nBody to plaintext of n as text
                    -- Truncate to avoid slow character-by-character escaping on large notes
                    if length of nBody > 3000 then set nBody to text 1 thru 3000 of nBody
                on error
                    set nBody to ""
                end try
                try
                    set nModDate to modification date of n as text
                on error
                    set nModDate to ""
                end try

                set rec to "{{\\"id\\": \\"" & my escapeJSON(nId) & "\\", \\"name\\": \\"" & my escapeJSON(nName) & "\\", \\"body\\": \\"" & my escapeJSON(nBody) & "\\", \\"modification_date\\": \\"" & my escapeJSON(nModDate) & "\\"}}"
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
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning("Notes AppleScript failed (rc=%s): %s", result.returncode, result.stderr.strip())
                return []
            output = result.stdout.strip()
            if not output or output == "[]":
                return []
            cleaned = "".join(char if (32 <= ord(char) < 127) else " " for char in output)
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Notes AppleScript output: %s", exc)
            return []
        except subprocess.TimeoutExpired:
            logger.warning("Notes AppleScript fetch timed out")
            return []
        except FileNotFoundError:
            logger.warning("osascript not found — Apple Notes ingress requires macOS")
            return []
        except Exception as exc:
            logger.warning("Unexpected error fetching notes: %s", exc)
            return []
