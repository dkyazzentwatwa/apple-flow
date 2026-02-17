"""Reads inbound emails from Apple Mail via AppleScript.

Polls the local Apple Mail app for unread messages from allowlisted senders,
converts them to InboundMessage objects (same as iMessage ingress), and marks
processed messages as read so they aren't re-fetched on the next poll.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone

from .models import InboundMessage
from .utils import normalize_sender

logger = logging.getLogger("codex_relay.mail_ingress")


class AppleMailIngress:
    """Reads inbound emails from the macOS Mail.app via AppleScript."""

    def __init__(self, account: str = "", mailbox: str = "INBOX"):
        self.account = account
        self.mailbox = mailbox
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
        for raw in raw_messages:
            msg_id = raw.get("id", "")
            sender_raw = raw.get("sender", "")
            subject = raw.get("subject", "")
            body = raw.get("body", "")
            date_str = raw.get("date", "")

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

        # Mark fetched messages as read so they are not re-processed
        if messages:
            fetched_ids = [raw.get("id", "") for raw in raw_messages]
            self._mark_as_read(fetched_ids)

        return messages[:limit]

    def latest_rowid(self) -> int | None:
        """Not applicable for Mail (uses unread status). Returns 0 as sentinel."""
        return 0

    def _fetch_unread_via_applescript(self, limit: int, sender_filter: list[str] | None = None) -> list[dict[str, str]]:
        """Run AppleScript to get unread emails as JSON.

        Args:
            limit: Maximum number of messages to fetch
            sender_filter: Optional list of email addresses to filter by (e.g., ["user@example.com"])
        """
        if self.account:
            mailbox_ref = f'mailbox "{self.mailbox}" of account "{self.account}"'
        else:
            mailbox_ref = "inbox"

        # Build sender filter clause for AppleScript
        if sender_filter:
            # Build: (sender contains "email1" or sender contains "email2")
            sender_conditions = []
            for email in sender_filter:
                # Escape quotes in email addresses
                escaped_email = email.replace('"', '\\"')
                sender_conditions.append(f'sender contains "{escaped_email}"')
            sender_clause = " or ".join(sender_conditions)
            where_clause = f"whose read status is false and ({sender_clause})"
        else:
            where_clause = "whose read status is false"

        script = f'''
        tell application "Mail"
            set maxCount to {int(limit)}
            set resultList to {{}}
            set unreadMessages to (every message of {mailbox_ref} {where_clause})
            set msgCount to count of unreadMessages
            if msgCount > maxCount then set msgCount to maxCount

            repeat with i from 1 to msgCount
                set msg to item i of unreadMessages
                set msgId to id of msg as text
                set msgSender to sender of msg as text
                set msgSubject to subject of msg as text
                try
                    set msgBody to content of msg as text
                on error
                    set msgBody to ""
                end try
                try
                    set msgDate to date received of msg as text
                on error
                    set msgDate to ""
                end try

                -- Build a JSON-ish delimited record
                set rec to "{{\\"id\\": \\"" & my escapeJSON(msgId) & "\\", \\"sender\\": \\"" & my escapeJSON(msgSender) & "\\", \\"subject\\": \\"" & my escapeJSON(msgSubject) & "\\", \\"body\\": \\"" & my escapeJSON(msgBody) & "\\", \\"date\\": \\"" & my escapeJSON(msgDate) & "\\"}}"
                set end of resultList to rec
            end repeat

            set AppleScript's text item delimiters to ","
            return "[" & (resultList as text) & "]"
        end tell

        on escapeJSON(txt)
            set output to ""
            repeat with ch in (characters of txt)
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
                logger.warning("AppleScript fetch failed (rc=%s): %s", result.returncode, result.stderr.strip())
                return []
            output = result.stdout.strip()
            if not output or output == "[]":
                return []
            return json.loads(output)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Mail AppleScript output: %s", exc)
            return []
        except subprocess.TimeoutExpired:
            logger.warning("AppleScript fetch timed out")
            return []
        except FileNotFoundError:
            logger.warning("osascript not found - Apple Mail ingress requires macOS")
            return []
        except Exception as exc:
            logger.warning("Unexpected error fetching mail: %s", exc)
            return []

    def _mark_as_read(self, message_ids: list[str]) -> None:
        """Mark processed emails as read so they are not re-polled."""
        if not message_ids:
            return

        if self.account:
            mailbox_ref = f'mailbox "{self.mailbox}" of account "{self.account}"'
        else:
            mailbox_ref = "inbox"

        # Build AppleScript to mark specific messages as read
        id_checks = " or ".join([f'(id of msg as text) is "{mid}"' for mid in message_ids if mid])
        if not id_checks:
            return

        script = f'''
        tell application "Mail"
            set msgs to every message of {mailbox_ref} whose read status is false
            repeat with msg in msgs
                if ({id_checks}) then
                    set read status of msg to true
                end if
            end repeat
        end tell
        '''

        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as exc:
            logger.warning("Failed to mark emails as read: %s", exc)

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
