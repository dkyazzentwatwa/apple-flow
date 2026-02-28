"""Reads inbound tasks from Apple Reminders via AppleScript.

Polls a designated Reminders list for incomplete reminders, converts them to
InboundMessage objects, and tracks processed IDs in the SQLite store to avoid
re-processing. Each reminder becomes a ``task:`` command for the AI assistant (or a
non-mutating command if ``auto_approve`` is enabled).
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone

from .models import InboundMessage
from .protocols import StoreProtocol
from .utils import normalize_sender

logger = logging.getLogger("apple_flow.reminders_ingress")

# Store keys for tracking processed reminders.
_PROCESSED_IDS_KEY = "reminders_processed_ids"
_PROCESSED_OCCURRENCES_KEY = "reminders_processed_occurrences"


class AppleRemindersIngress:
    """Reads incomplete reminders from a designated Reminders.app list."""

    def __init__(
        self,
        list_name: str = "agent-task",
        owner_sender: str = "",
        auto_approve: bool = False,
        trigger_tag: str = "",
        due_delay_seconds: int = 60,
        store: StoreProtocol | None = None,
    ):
        self.list_name = list_name
        self.owner_sender = normalize_sender(owner_sender)
        self.auto_approve = auto_approve
        self.trigger_tag = trigger_tag.strip()
        self.due_delay_seconds = max(0, int(due_delay_seconds))
        self._store = store
        self._processed_occurrences: set[str] = set()
        # Hydrate processed occurrence keys from persistent store on startup.
        if store is not None:
            raw_occurrences = store.get_state(_PROCESSED_OCCURRENCES_KEY)
            if raw_occurrences:
                try:
                    self._processed_occurrences = set(json.loads(raw_occurrences))
                except (json.JSONDecodeError, TypeError):
                    self._processed_occurrences = set()
            else:
                # Backward-compatible migration from reminder-id-only dedupe.
                raw_ids = store.get_state(_PROCESSED_IDS_KEY)
                if raw_ids:
                    try:
                        legacy_ids = set(json.loads(raw_ids))
                    except (json.JSONDecodeError, TypeError):
                        legacy_ids = set()
                    self._processed_occurrences = {self._occurrence_key(reminder_id, "") for reminder_id in legacy_ids}
                    self._persist_processed_occurrences()

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

            name = (raw.get("name", "") or "").strip()
            body = (raw.get("body", "") or "").strip()
            creation_date = raw.get("creation_date", "")
            due_date = raw.get("due_date", "")
            occurrence_key = self._occurrence_key(reminder_id, due_date)

            # Skip already-processed occurrences.
            if occurrence_key in self._processed_occurrences:
                continue

            # Skip reminders that don't contain the trigger tag (if configured).
            if self.trigger_tag:
                if self.trigger_tag not in name and self.trigger_tag not in body:
                    continue
                name = name.replace(self.trigger_tag, "").strip()
                body = body.replace(self.trigger_tag, "").strip()

            # Due-tagged reminders are dispatched only after due time + configured delay.
            if due_date:
                due_at = self._parse_due_date(due_date)
                if due_at is None:
                    logger.warning(
                        "Skipping reminder id=%s due to unparseable due date: %r",
                        reminder_id,
                        due_date,
                    )
                    continue
                cutoff = datetime.now() - timedelta(seconds=self.due_delay_seconds)
                if due_at > cutoff:
                    continue

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
                        "occurrence_key": occurrence_key,
                        "reminder_name": name,
                        "list_name": self.list_name,
                    },
                )
            )

        return messages[:limit]

    def mark_processed_occurrence(self, occurrence_key: str) -> None:
        """Record an occurrence key as processed so it won't be fetched again."""
        if not occurrence_key:
            return
        self._processed_occurrences.add(occurrence_key)
        self._persist_processed_occurrences()

    def mark_processed(self, reminder_id: str) -> None:
        """Backward-compatible helper for id-only callers."""
        self.mark_processed_occurrence(self._occurrence_key(reminder_id, ""))

    def latest_rowid(self) -> int | None:
        """Not applicable for Reminders.  Returns 0 as sentinel."""
        return 0

    def _persist_processed_occurrences(self) -> None:
        """Persist processed reminder occurrence keys to the store."""
        if self._store is not None:
            self._store.set_state(_PROCESSED_OCCURRENCES_KEY, json.dumps(sorted(self._processed_occurrences)))

    def _fetch_incomplete_via_applescript(self, limit: int) -> list[dict[str, str]]:
        """Run AppleScript to get incomplete reminders as tab-delimited records.

        Performance: O(N) where N is the total text size, using bulk string
        replacements instead of character-by-character loops.
        """
        escaped_list_name = self.list_name.replace('"', '\\"')

        script = f'''
        on pad2(n)
            set nStr to n as text
            if (length of nStr) is 1 then
                return "0" & nStr
            end if
            return nStr
        end pad2

        on isoLocalDate(d)
            set y to year of d as integer
            set m to month of d as integer
            set dd to day of d as integer
            set hh to hours of d as integer
            set mm to minutes of d as integer
            set ss to seconds of d as integer
            return (y as text) & "-" & my pad2(m) & "-" & my pad2(dd) & " " & my pad2(hh) & ":" & my pad2(mm) & ":" & my pad2(ss)
        end isoLocalDate

        on sanitise(txt)
            set AppleScript's text item delimiters to tab
            set parts to text items of txt
            set AppleScript's text item delimiters to " "
            set txt to parts as text
            set AppleScript's text item delimiters to linefeed
            set parts to text items of txt
            set AppleScript's text item delimiters to " "
            set txt to parts as text
            set AppleScript's text item delimiters to return
            set parts to text items of txt
            set AppleScript's text item delimiters to " "
            set txt to parts as text
            set AppleScript's text item delimiters to ""
            return txt
        end sanitise

        tell application "Reminders"
            set maxCount to {int(limit)}
            set outputLines to {{}}

            try
                set taskList to list "{escaped_list_name}"
            on error
                return ""
            end try

            set openItems to (every reminder of taskList whose completed is false)

            repeat with rem in openItems
                if (count of outputLines) >= maxCount then exit repeat

                set rId to id of rem
                if rId is missing value then
                    set rIdStr to ""
                else
                    set rIdStr to my sanitise(rId as text)
                end if

                set rName to name of rem
                if rName is missing value then
                    set rNameStr to ""
                else
                    set rNameStr to my sanitise(rName as text)
                end if

                try
                    set rBody to body of rem
                    if rBody is missing value then
                        set rBodyStr to ""
                    else
                        set rBodyText to rBody as text
                        if length of rBodyText > 4000 then set rBodyText to text 1 thru 4000 of rBodyText
                        set rBodyStr to my sanitise(rBodyText)
                    end if
                on error
                    set rBodyStr to ""
                end try

                try
                    set rCreation to creation date of rem
                    if rCreation is missing value then
                        set rCreationStr to ""
                    else
                        set rCreationStr to my sanitise(rCreation as text)
                    end if
                on error
                    set rCreationStr to ""
                end try

                try
                    set rDue to due date of rem
                    if rDue is missing value then
                        set rDueStr to ""
                    else
                        try
                            set rDueStr to my isoLocalDate(rDue)
                        on error
                            set rDueStr to my sanitise(rDue as text)
                        end try
                    end if
                on error
                    set rDueStr to ""
                end try

                set end of outputLines to rIdStr & tab & rNameStr & tab & rBodyStr & tab & rCreationStr & tab & rDueStr
            end repeat

            set AppleScript's text item delimiters to linefeed
            return (outputLines as text)
        end tell
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
            if not output:
                return []
            return self._parse_tab_delimited(output)
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
    def _parse_tab_delimited(output: str) -> list[dict[str, str]]:
        """Parse tab-delimited reminders output into list of dicts."""
        reminders: list[dict[str, str]] = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            reminders.append({
                "id": parts[0],
                "name": parts[1],
                "body": parts[2],
                "creation_date": parts[3],
                "due_date": parts[4],
            })
        return reminders

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

    @staticmethod
    def _occurrence_key(reminder_id: str, due_date: str) -> str:
        return f"{reminder_id}|{due_date.strip()}"

    @staticmethod
    def _parse_due_date(value: str) -> datetime | None:
        """Parse reminder due date text into a local naive datetime."""
        raw = (value or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"

        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is not None:
                return parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            pass

        known_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%a %b %d %H:%M:%S %Z %Y",
            "%a %b %d %H:%M:%S %Y",
        ]
        for fmt in known_formats:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None
