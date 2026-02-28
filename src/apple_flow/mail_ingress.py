"""Reads inbound emails from Apple Mail via AppleScript.

Polls the local Apple Mail app for unread messages from allowlisted senders,
converts them to InboundMessage objects (same as iMessage ingress), and marks
processed messages as read so they aren't re-fetched on the next poll.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone

from .models import InboundMessage
from .utils import normalize_sender

logger = logging.getLogger("apple_flow.mail_ingress")


class AppleMailIngress:
    """Reads inbound emails from the macOS Mail.app via AppleScript."""

    def __init__(self, account: str = "", mailbox: str = "INBOX", max_age_days: int = 2, trigger_tag: str = ""):
        self.account = account
        self.mailbox = mailbox
        self.max_age_days = max_age_days
        self.trigger_tag = trigger_tag.strip()
        self._last_seen_ids: set[str] = set()

    def fetch_new(
        self,
        since_rowid: int | None = None,
        limit: int = 50,
        sender_allowlist: list[str] | None = None,
        require_sender_filter: bool = False,
    ) -> list[InboundMessage]:
        """Fetch unread emails from Apple Mail.

        Parameters mirror IMessageIngress.fetch_new() for interface compatibility.
        ``since_rowid`` is unused (Mail uses unread status instead of rowids).
        """
        if require_sender_filter and not sender_allowlist:
            return []

        # Extract email addresses from allowlist for AppleScript filtering
        email_filters: list[str] | None = None
        if sender_allowlist:
            email_filters = []
            for s in sender_allowlist:
                # Extract just the email part (strips phone numbers, normalizes)
                email = self._extract_email_address(s)
                if email and "@" in email:
                    email_filters.append(email.lower())

        raw_messages = self._fetch_unread_via_applescript(limit, sender_filter=email_filters)
        messages: list[InboundMessage] = []
        processed_ids: list[str] = []
        for raw in raw_messages:
            msg_id = raw.get("id", "")
            sender_raw = raw.get("sender", "")
            subject = (raw.get("subject", "") or "").strip()
            body = (raw.get("body", "") or "").strip()
            date_str = raw.get("date", "")

            # Skip emails that don't contain the trigger tag (if configured).
            # Do NOT mark as read — leave them unread so they can be picked up later.
            if self.trigger_tag:
                if self.trigger_tag not in subject and self.trigger_tag not in body:
                    continue
                subject = subject.replace(self.trigger_tag, "").strip()
                body = body.replace(self.trigger_tag, "").strip()

            sender = self._extract_email_address(sender_raw)

            # Combine subject and body for the task text
            text = self._compose_text(subject, body)
            if not text.strip():
                continue

            received_at = date_str or datetime.now(timezone.utc).isoformat()

            messages.append(
                InboundMessage(
                    id=f"mail_{msg_id}",
                    sender=normalize_sender(sender),
                    text=text,
                    received_at=received_at,
                    is_from_me=False,
                )
            )
            processed_ids.append(msg_id)

        # Mark only processed messages as read so they are not re-polled.
        if processed_ids:
            read_outcomes = self._mark_as_read(processed_ids)
            if not isinstance(read_outcomes, dict):
                read_outcomes = {}
            not_found_ids = [msg_id for msg_id, status in read_outcomes.items() if status == "not_found"]
            error_ids = [msg_id for msg_id, status in read_outcomes.items() if status == "error"]
            fallback_matches = sum(1 for status in read_outcomes.values() if status == "fallback_matched")
            if fallback_matches:
                logger.info(
                    "Mail read-state fallback matched %s message(s) outside mailbox=%r",
                    fallback_matches,
                    self.mailbox,
                )
            if not_found_ids:
                logger.warning(
                    "Could not mark %s email(s) as read (not found after fallback): %s",
                    len(not_found_ids),
                    ", ".join(not_found_ids[:10]),
                )
            if error_ids:
                logger.warning(
                    "Failed to mark %s email(s) as read due to AppleScript errors: %s",
                    len(error_ids),
                    ", ".join(error_ids[:10]),
                )

        return messages[:limit]

    def latest_rowid(self) -> int | None:
        """Not applicable for Mail (uses unread status). Returns 0 as sentinel."""
        return 0

    def _fetch_unread_via_applescript(self, limit: int, sender_filter: list[str] | None = None) -> list[dict[str, str]]:
        """Run AppleScript to get unread emails as tab-delimited records.

        Args:
            limit: Maximum number of messages to fetch
            sender_filter: Optional list of email addresses to filter by (e.g., ["user@example.com"])
        """
        if self.account:
            mailbox_ref = f'mailbox "{self.mailbox}" of account "{self.account}"'
        else:
            mailbox_ref = "inbox"

        # Build sender filter clause for AppleScript
        conditions = ["read status is false"]

        if sender_filter:
            # Build: (sender contains "email1" or sender contains "email2")
            sender_conditions = []
            for email in sender_filter:
                # Escape quotes in email addresses
                escaped_email = email.replace('"', '\\"')
                sender_conditions.append(f'sender contains "{escaped_email}"')
            sender_clause = "(" + " or ".join(sender_conditions) + ")"
            conditions.append(sender_clause)

        where_clause = f"whose {' and '.join(conditions)}"

        script = f'''
        on sanitise(txt)
            -- Replace tabs with spaces
            set AppleScript's text item delimiters to character id 9
            set parts to text items of txt
            set AppleScript's text item delimiters to " "
            set txt to parts as text
            -- Replace newlines (LF) with spaces
            set AppleScript's text item delimiters to character id 10
            set parts to text items of txt
            set AppleScript's text item delimiters to " "
            set txt to parts as text
            -- Replace carriage returns with spaces
            set AppleScript's text item delimiters to character id 13
            set parts to text items of txt
            set AppleScript's text item delimiters to " "
            set txt to parts as text
            set AppleScript's text item delimiters to ""
            return txt
        end sanitise

        tell application "Mail"
            set maxCount to {int(limit)}
            set outputLines to {{}}
            set maxAgeDays to {int(self.max_age_days)}
            set cutoffDate to (current date) - (maxAgeDays * days)

            set unreadMessages to (every message of {mailbox_ref} {where_clause})

            repeat with msg in unreadMessages
                -- Stop if we have enough messages
                if (count of outputLines) >= maxCount then exit repeat

                -- Check if message is recent enough
                set msgDateReceived to date received of msg
                if msgDateReceived < cutoffDate then
                    -- Skip old messages
                else
                    set msgId to my sanitise(id of msg as text)
                    set msgSender to my sanitise(sender of msg as text)
                    set msgSubject to my sanitise(subject of msg as text)
                    try
                        set msgBody to content of msg as text
                        if length of msgBody > 4000 then set msgBody to text 1 thru 4000 of msgBody
                        set msgBody to my sanitise(msgBody)
                    on error
                        set msgBody to ""
                    end try
                    try
                        set msgDate to my sanitise(date received of msg as text)
                    on error
                        set msgDate to ""
                    end try

                    set end of outputLines to msgId & character id 9 & msgSender & character id 9 & msgSubject & character id 9 & msgBody & character id 9 & msgDate
                end if
            end repeat

            set AppleScript's text item delimiters to character id 10
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
                logger.warning("AppleScript fetch failed (rc=%s): %s", result.returncode, result.stderr.strip())
                return []
            output = result.stdout.strip()
            if not output:
                return []
            return self._parse_tab_delimited(output)
        except subprocess.TimeoutExpired:
            logger.warning("AppleScript fetch timed out")
            return []
        except FileNotFoundError:
            logger.warning("osascript not found - Apple Mail ingress requires macOS")
            return []
        except Exception as exc:
            logger.warning("Unexpected error fetching mail: %s", exc)
            return []

    @staticmethod
    def _parse_tab_delimited(output: str) -> list[dict[str, str]]:
        """Parse tab-delimited mail output into list of dicts."""
        messages: list[dict[str, str]] = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            messages.append({
                "id": parts[0],
                "sender": parts[1],
                "subject": parts[2],
                "body": parts[3],
                "date": parts[4],
            })
        return messages

    def _mark_as_read(self, message_ids: list[str]) -> dict[str, str]:
        """Mark processed emails as read so they are not re-polled.

        Returns:
            Mapping of message id -> status where status is one of:
            matched, fallback_matched, not_found, error
        """
        if not message_ids:
            return {}

        if self.account:
            mailbox_ref = f'mailbox "{self.mailbox}" of account "{self.account}"'
        else:
            mailbox_ref = "inbox"

        sanitized_ids = [mid.replace(chr(34), "") for mid in message_ids if mid]
        if not sanitized_ids:
            return {}

        def _id_match_clause(mid: str) -> str:
            if mid.isdigit():
                return f"id is {int(mid)}"
            return f'id as text is "{mid}"'

        def _id_block(mid: str) -> str:
            id_match = _id_match_clause(mid)
            return f'''
\tset statusForId to "not_found"
\tset resolvedMsg to missing value
\tset foundInPrimary to false
\ttry
\t\tset resolvedMsg to first message of {mailbox_ref} whose {id_match}
\t\tset foundInPrimary to true
\ton error
\t\tset resolvedMsg to missing value
\tend try
\tif resolvedMsg is missing value then
\t\trepeat with acc in every account
\t\t\tset accountMailboxes to every mailbox of acc
\t\t\trepeat with boxRef in accountMailboxes
\t\t\t\ttry
\t\t\t\t\tset resolvedMsg to first message of boxRef whose {id_match}
\t\t\t\t\texit repeat
\t\t\t\ton error
\t\t\t\t\tset resolvedMsg to missing value
\t\t\t\tend try
\t\t\tend repeat
\t\t\tif resolvedMsg is not missing value then exit repeat
\t\tend repeat
\tend if
\tif resolvedMsg is missing value then
\t\tset statusForId to "not_found"
\telse
\t\ttry
\t\t\tset read status of resolvedMsg to true
\t\t\tif foundInPrimary then
\t\t\t\tset statusForId to "matched"
\t\t\telse
\t\t\t\tset statusForId to "fallback_matched"
\t\t\tend if
\t\ton error
\t\t\tset statusForId to "error"
\t\tend try
\tend if
\tset end of outputLines to "{mid}" & character id 9 & statusForId
'''

        id_lines = "\n".join(_id_block(mid) for mid in sanitized_ids)
        script = f'''tell application "Mail"
\tset outputLines to {{}}
{id_lines}
\tset AppleScript's text item delimiters to character id 10
\treturn (outputLines as text)
end tell'''

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(
                    "Failed to mark emails as read (rc=%s): %s",
                    result.returncode,
                    result.stderr.strip() or "Unknown AppleScript error",
                )
                return {mid: "error" for mid in sanitized_ids}
            return self._parse_mark_read_outcomes(result.stdout, sanitized_ids)
        except Exception as exc:
            logger.warning("Failed to mark %s email(s) as read: %s", len(sanitized_ids), exc)
            return {mid: "error" for mid in sanitized_ids}

    @staticmethod
    def _parse_mark_read_outcomes(output: str, message_ids: list[str]) -> dict[str, str]:
        outcomes: dict[str, str] = {}
        valid_statuses = {"matched", "fallback_matched", "not_found", "error"}
        for line in (output or "").splitlines():
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            msg_id, status = parts[0].strip(), parts[1].strip()
            if not msg_id:
                continue
            if status not in valid_statuses:
                status = "error"
            outcomes[msg_id] = status
        for msg_id in message_ids:
            if msg_id not in outcomes:
                outcomes[msg_id] = "error"
        return outcomes

    @staticmethod
    def _extract_email_address(sender_raw: str) -> str:
        """Extract email address from a sender string like 'Name <email@example.com>'."""
        if "<" in sender_raw and ">" in sender_raw:
            start = sender_raw.index("<") + 1
            end = sender_raw.index(">")
            return sender_raw[start:end].strip()
        return sender_raw.strip()

    @staticmethod
    def _compose_text(subject: str, body: str) -> str:
        """Combine subject and body into a single text for processing.

        If the subject already contains a command prefix (relay:, task:, etc.),
        the subject line becomes the command and the body provides context.
        """
        subject = (subject or "").strip()
        body = (body or "").strip()

        if not subject and not body:
            return ""
        if not body:
            return subject
        if not subject:
            return body

        return f"{subject}\n\n{body}"
