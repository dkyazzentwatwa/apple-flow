"""Reads inbound tasks from Apple Notes via AppleScript.

Polls a designated Notes folder for notes, converts them to InboundMessage
objects, and tracks processed note IDs in the SQLite store.  Each note becomes
a command for Codex (title may contain a prefix like ``task:``).
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
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
        fetch_timeout_seconds: float = 20.0,
        fetch_retries: int = 1,
        fetch_retry_delay_seconds: float = 1.5,
        store: StoreProtocol | None = None,
    ):
        self.folder_name = folder_name
        self.trigger_tag = trigger_tag.strip()
        self.owner_sender = owner_sender
        self.auto_approve = auto_approve
        self.fetch_timeout_seconds = fetch_timeout_seconds
        self.fetch_retries = max(0, int(fetch_retries))
        self.fetch_retry_delay_seconds = max(0.0, float(fetch_retry_delay_seconds))
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

            text = self._compose_text(title, body, self.trigger_tag)
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
    def _compose_text(title: str, body: str, trigger_tag: str = "") -> str:
        """Compose the prompt text from note title and body, stripping the trigger tag."""
        def strip_tag(s: str) -> str:
            if trigger_tag:
                s = s.replace(trigger_tag, "").strip()
            return s

        title = strip_tag(title)
        body = strip_tag(body)

        if not title and not body:
            return ""
        if not body:
            return title
        if not title:
            return body
        # Avoid duplicating content when Notes echoes the title as the first line of body
        body_first_line = body.split("\n")[0].strip()
        if body_first_line == title:
            return title
        return f"{title}\n\n{body}"

    def _fetch_notes_via_applescript(self, limit: int) -> list[dict[str, str]]:
        escaped_folder = self.folder_name.replace('"', '\\"')

        # Tab-delimited output: one note per line as id<TAB>name<TAB>body<TAB>mod_date.
        # Tabs and newlines within fields are replaced with spaces using fast
        # AppleScript text-item-delimiter substitution instead of the slow
        # character-by-character escapeJSON handler.
        script = f'''
        on sanitise(txt)
            -- Replace tabs with spaces
            set AppleScript's text item delimiters to (ASCII character 9)
            set parts to text items of txt
            set AppleScript's text item delimiters to " "
            set txt to parts as text
            -- Replace newlines (LF) with spaces
            set AppleScript's text item delimiters to (ASCII character 10)
            set parts to text items of txt
            set AppleScript's text item delimiters to " "
            set txt to parts as text
            -- Replace carriage returns with spaces
            set AppleScript's text item delimiters to (ASCII character 13)
            set parts to text items of txt
            set AppleScript's text item delimiters to " "
            set txt to parts as text
            set AppleScript's text item delimiters to ""
            return txt
        end sanitise

        tell application "Notes"
            set maxCount to {int(limit)}
            set outputLines to {{}}

            try
                set targetFolder to folder "{escaped_folder}"
            on error
                return ""
            end try

            set allNotes to every note of targetFolder

            repeat with n in allNotes
                if (count of outputLines) >= maxCount then exit repeat

                set nId to my sanitise(id of n as text)
                set nName to my sanitise(name of n as text)
                try
                    set nBody to plaintext of n as text
                    if length of nBody > 4000 then set nBody to text 1 thru 4000 of nBody
                    set nBody to my sanitise(nBody)
                on error
                    set nBody to ""
                end try
                try
                    set nModDate to my sanitise(modification date of n as text)
                on error
                    set nModDate to ""
                end try

                set end of outputLines to nId & (ASCII character 9) & nName & (ASCII character 9) & nBody & (ASCII character 9) & nModDate
            end repeat

            set AppleScript's text item delimiters to (ASCII character 10)
            return (outputLines as text)
        end tell
        '''

        max_attempts = self.fetch_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=self.fetch_timeout_seconds,
                )
                if result.returncode != 0:
                    logger.warning("Notes AppleScript failed (rc=%s): %s", result.returncode, result.stderr.strip())
                    return []
                output = result.stdout.strip()
                if not output:
                    return []
                return self._parse_tab_delimited(output)
            except subprocess.TimeoutExpired:
                if attempt >= max_attempts:
                    logger.warning(
                        "Notes AppleScript fetch timed out after %d attempt(s)", max_attempts
                    )
                    return []
                logger.warning(
                    "Notes AppleScript fetch timed out (attempt %d/%d); retrying in %.1fs",
                    attempt,
                    max_attempts,
                    self.fetch_retry_delay_seconds,
                )
                time.sleep(self.fetch_retry_delay_seconds)
            except FileNotFoundError:
                logger.warning("osascript not found — Apple Notes ingress requires macOS")
                return []
            except Exception as exc:
                logger.warning("Unexpected error fetching notes: %s", exc)
                return []
        return []

    @staticmethod
    def _parse_tab_delimited(output: str) -> list[dict[str, str]]:
        """Parse tab-delimited notes output into list of dicts."""
        notes: list[dict[str, str]] = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            notes.append({
                "id": parts[0],
                "name": parts[1],
                "body": parts[2],
                "modification_date": parts[3],
            })
        return notes
