"""Sends outbound emails via Apple Mail AppleScript.

Mirrors the IMessageEgress pattern: chunking, retry, deduplication, and echo
detection — but sends email via Mail.app instead of iMessage.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import time

from .utils import normalize_sender

logger = logging.getLogger("codex_relay.mail_egress")


class AppleMailEgress:
    """Sends outbound emails via macOS Mail.app AppleScript."""

    def __init__(
        self,
        from_address: str = "",
        max_chunk_chars: int = 50000,
        retries: int = 3,
        echo_window_seconds: float = 300.0,
        suppress_duplicate_outbound_seconds: float = 120.0,
    ):
        self.from_address = from_address
        self.max_chunk_chars = max_chunk_chars
        self.retries = retries
        self.echo_window_seconds = echo_window_seconds
        self.suppress_duplicate_outbound_seconds = suppress_duplicate_outbound_seconds
        self._recent_fingerprints: dict[str, float] = {}

    def send(self, recipient: str, text: str) -> None:
        """Send an email reply to the recipient.

        Implements deduplication and chunking consistent with IMessageEgress.
        """
        outbound_fingerprint = self._fingerprint(recipient, text)
        last_ts = self._recent_fingerprints.get(outbound_fingerprint)
        if last_ts is not None and (time.time() - last_ts) <= self.suppress_duplicate_outbound_seconds:
            logger.info(
                "Suppressing duplicate outbound email to %s (%s chars) within %.1fs window",
                recipient,
                len(text),
                self.suppress_duplicate_outbound_seconds,
            )
            return

        logger.info("Sending email to %s (%s chars)", recipient, len(text))
        chunks = self._chunk(text)
        for i, chunk in enumerate(chunks):
            subject = "Codex Relay Response"
            if len(chunks) > 1:
                subject = f"Codex Relay Response (part {i + 1}/{len(chunks)})"

            last_error: Exception | None = None
            for attempt in range(1, self.retries + 1):
                try:
                    self._osascript_send(recipient, subject, chunk)
                    self.mark_outbound(recipient, chunk)
                    logger.info("Sent email chunk to %s (%s chars)", recipient, len(chunk))
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning("Email send retry %s failed for %s: %s", attempt, recipient, exc)
                    time.sleep(0.5 * attempt)
            if last_error is not None:
                raise RuntimeError(f"Failed to send email after retries: {last_error}") from last_error

    def _osascript_send(self, recipient: str, subject: str, body: str) -> None:
        """Send an email using Apple Mail via osascript."""
        escaped_body = body.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        escaped_subject = subject.replace("\\", "\\\\").replace('"', '\\"')
        escaped_recipient = recipient.replace("\\", "\\\\").replace('"', '\\"')

        if self.from_address:
            escaped_from = self.from_address.replace("\\", "\\\\").replace('"', '\\"')
            sender_prop = f', sender:"{escaped_from}"'
        else:
            sender_prop = ""

        script = f'''
        tell application "Mail"
            set newMessage to make new outgoing message with properties {{subject:"{escaped_subject}", content:"{escaped_body}", visible:false{sender_prop}}}
            tell newMessage
                make new to recipient at end of to recipients with properties {{address:"{escaped_recipient}"}}
            end tell
            send newMessage
        end tell
        '''

        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _chunk(self, text: str) -> list[str]:
        """Split text into chunks for email (larger threshold than iMessage)."""
        if len(text) <= self.max_chunk_chars:
            return [text]
        chunks = []
        remaining = text
        while remaining:
            chunks.append(remaining[: self.max_chunk_chars])
            remaining = remaining[self.max_chunk_chars :]
        return chunks

    def _fingerprint(self, handle: str, text: str) -> str:
        normalized = normalize_sender(handle)
        normalized_text = self._normalize_text(text)
        payload = f"mail:{normalized}:{normalized_text}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = (text or "").replace("\u2019", "'").replace("\u2018", "'")
        cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
        return cleaned

    def _gc_recent(self) -> None:
        now = time.time()
        expired = [
            fp for fp, ts in self._recent_fingerprints.items() if (now - ts) > self.echo_window_seconds
        ]
        for fp in expired:
            self._recent_fingerprints.pop(fp, None)

    def was_recent_outbound(self, sender: str, text: str) -> bool:
        self._gc_recent()
        return self._fingerprint(sender, text) in self._recent_fingerprints

    def mark_outbound(self, recipient: str, text: str) -> None:
        self._gc_recent()
        self._recent_fingerprints[self._fingerprint(recipient, text)] = time.time()
