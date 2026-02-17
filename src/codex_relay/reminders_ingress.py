"""Reads inbound tasks from Apple Reminders via AppleScript.

Polls a designated Reminders list for incomplete reminders, converts them to
InboundMessage objects, and tracks processed IDs in the SQLite store to avoid
re-processing.  Each reminder becomes a ``task:`` command for Codex (or a
non-mutating command if ``auto_approve`` is enabled).
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone

from .models import InboundMessage
from .protocols import StoreProtocol

logger = logging.getLogger("codex_relay.reminders_ingress")

# Store key prefix for tracking which reminder IDs have been processed.
_PROCESSED_IDS_KEY = "reminders_processed_ids"


class AppleRemindersIngress:
    """Reads incomplete reminders from a designated Reminders.app list."""

    def __init__(
        self,
        list_name: str = "Codex Tasks",
        owner_sender: str = "",
        auto_approve: bool = False,
        store: StoreProtocol | None = None,
    ):
        self.list_name = list_name
        self.owner_sender = owner_sender
        self.auto_approve = auto_approve
        self._store = store
        self._processed_ids: set[str] = set()
        # Hydrate processed IDs from persistent store on startup.
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
        limit: int = 50,
        sender_allowlist: list[str] | None = None,
        require_sender_filter: bool = False,
    ) -> list[InboundMessage]:
        """Fetch incomplete reminders from the designated list.

        Parameters mirror the ingress interface for compatibility.
        ``since_rowid`` and ``sender_allowlist`` are unused (Reminders is local-only).
        """
        raw_reminders = self._fetch_incomplete_via_applescript(limit)
        messages: list[InboundMessage] = []

        for raw in raw_reminders:
            reminder_id = raw.get("id", "")
            if not reminder_id:
                continue

            # Skip already-processed reminders.
            if reminder_id in self._processed_ids:
                continue

            name = (raw.get("name", "") or "").strip()
            body = (raw.get("body", "") or "").strip()
            creation_date = raw.get("creation_date", "")
            due_date = raw.get("due_date", "")

            # Build the task text from reminder name + notes.
            text = self._compose_text(name, body, due_date)
            if not text:
                continue

            # Prefix with task: or idea: depending on auto_approve setting.
            if self.auto_approve:
                prefixed_text = f"relay: {text}"
            else:
                prefixed_text = f"task: {text}"

            received_at = creation_date or datetime.now(timezone.utc).isoformat()

            messages.append(
                InboundMessage(
                    id=f"reminder_{reminder_id}",
                    sender=self.owner_sender,
                    text=prefixed_text,
                    received_at=received_at,
                    is_from_me=False,
                    context={
                        "channel": "reminders",
                        "reminder_id": reminder_id,
                        "reminder_name": name,
                        "list_name": self.list_name,
                    },
                )
            )

        return messages[:limit]

    def mark_processed(self, reminder_id: str) -> None:
        """Record a reminder ID as processed so it won't be fetched again."""
        self._processed_ids.add(reminder_id)
        self._persist_processed_ids()

    def latest_rowid(self) -> int | None:
        """Not applicable for Reminders.  Returns 0 as sentinel."""
        return 0

    def _persist_processed_ids(self) -> None:
        """Persist the set of processed reminder IDs to the store."""
        if self._store is not None:
            self._store.set_state(_PROCESSED_IDS_KEY, json.dumps(sorted(self._processed_ids)))

    def _fetch_incomplete_via_applescript(self, limit: int) -> list[dict[str, str]]:
        """Run AppleScript to get incomplete reminders as JSON."""
        escaped_list_name = self.list_name.replace('"', '\\"')

        script = f'''
        tell application "Reminders"
            set maxCount to {int(limit)}
            set resultList to {{}}

            try
                set taskList to list "{escaped_list_name}"
            on error
                return "[]"
            end try

            set openItems to (every reminder of taskList whose completed is false)

            repeat with rem in openItems
                if (count of resultList) >= maxCount then exit repeat

                set remId to id of rem as text
                set remName to name of rem as text
                try
                    set remBody to body of rem as text
                on error
                    set remBody to ""
                end try
                try
                    set remCreation to creation date of rem as text
                on error
                    set remCreation to ""
                end try
                try
                    set remDue to due date of rem as text
                on error
                    set remDue to ""
                end try

                set rec to "{{\\"id\\": \\"" & my escapeJSON(remId) & "\\", \\"name\\": \\"" & my escapeJSON(remName) & "\\", \\"body\\": \\"" & my escapeJSON(remBody) & "\\", \\"creation_date\\": \\"" & my escapeJSON(remCreation) & "\\", \\"due_date\\": \\"" & my escapeJSON(remDue) & "\\"}}"
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
                logger.warning(
                    "Reminders AppleScript failed (rc=%s): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return []
            output = result.stdout.strip()
            if not output or output == "[]":
                return []

            # Clean control characters before parsing JSON.
            cleaned = "".join(
                char if (32 <= ord(char) < 127) else " " for char in output
            )
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Reminders AppleScript output: %s", exc)
            return []
        except subprocess.TimeoutExpired:
            logger.warning("Reminders AppleScript fetch timed out")
            return []
        except FileNotFoundError:
            logger.warning("osascript not found — Apple Reminders ingress requires macOS")
            return []
        except Exception as exc:
            logger.warning("Unexpected error fetching reminders: %s", exc)
            return []

    @staticmethod
    def _compose_text(name: str, body: str, due_date: str) -> str:
        """Build task text from reminder name, notes, and optional due date."""
        parts: list[str] = []
        if name:
            parts.append(name)
        if due_date:
            parts.append(f"[due: {due_date}]")
        if body:
            parts.append(f"\n\n{body}")
        return " ".join(parts) if len(parts) <= 2 and not body else "\n".join(filter(None, [
            f"{name} [due: {due_date}]" if name and due_date else name,
            body,
        ]))
