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

logger = logging.getLogger("apple_flow.mail_egress")


class AppleMailEgress:
    """Sends outbound emails via macOS Mail.app AppleScript."""

    def __init__(
        self,
        from_address: str = "",
        response_subject: str = "AGENT:",
        max_chunk_chars: int = 50000,
        retries: int = 3,
        echo_window_seconds: float = 300.0,
        suppress_duplicate_outbound_seconds: float = 120.0,
        signature: str = "\n\n—\nApple Flow 🤖, Your 24/7 Assistant",
    ):
        self.from_address = from_address
        self.response_subject = response_subject or "AGENT:"
        self.max_chunk_chars = max_chunk_chars
        self.retries = retries
        self.echo_window_seconds = echo_window_seconds
        self.suppress_duplicate_outbound_seconds = suppress_duplicate_outbound_seconds
        # Convert literal \n from env settings (enable_decoding=False) to real newlines
        self.signature = signature.replace("\\n", "\n")
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

        # Add signature to the text
        text_with_signature = text + self.signature

        logger.info("Sending email to %s (%s chars)", recipient, len(text_with_signature))
        chunks = self._chunk(text_with_signature)
        for chunk in chunks:
            last_error: Exception | None = None
            for attempt in range(1, self.retries + 1):
                try:
                    self._osascript_send(recipient, self.response_subject, chunk)
                    logger.info("Sent email chunk to %s (%s chars)", recipient, len(chunk))
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning("Email send retry %s failed for %s: %s", attempt, recipient, exc)
                    time.sleep(0.5 * attempt)
            if last_error is not None:
                raise RuntimeError(f"Failed to send email after retries: {last_error}") from last_error

        # Mark outbound using original text (without signature) for fingerprint consistency
        # This ensures the dedup check at the top of send() matches what we record here
        self.mark_outbound(recipient, text)

    def _osascript_send(self, recipient: str, subject: str, body: str) -> None:
        """Send an outbound email via Apple Mail using osascript."""
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

    def send_attachment(self, recipient: str, file_path: str) -> None:
        """Send a file as an email attachment via Mail.app."""
        if not file_path:
            return
        try:
            self._osascript_send_attachment(recipient, file_path)
            logger.info("Sent email attachment to %s: %s", recipient, file_path)
        except Exception as exc:
            logger.warning("Failed to send email attachment to %s: %s", recipient, exc)

    def _osascript_send_attachment(self, recipient: str, file_path: str) -> None:
        """Attach a file to an outgoing email via AppleScript."""
        escaped_recipient = recipient.replace("\\", "\\\\").replace('"', '\\"')
        escaped_path = file_path.replace("\\", "\\\\").replace('"', '\\"')

        if self.from_address:
            escaped_from = self.from_address.replace("\\", "\\\\").replace('"', '\\"')
            sender_prop = f', sender:"{escaped_from}"'
        else:
            sender_prop = ""

        script = f'''
        tell application "Mail"
            set newMessage to make new outgoing message with properties {{subject:"Apple Flow Voice Memo", content:"Voice memo attached.", visible:false{sender_prop}}}
            tell newMessage
                make new to recipient at end of to recipients with properties {{address:"{escaped_recipient}"}}
                make new attachment with properties {{file name:(POSIX file "{escaped_path}" as alias)}} at after the last paragraph
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
        if self._fingerprint(sender, text) in self._recent_fingerprints:
            return True
        # Strip "Re: <subject>\n\n" prefix added by mail client on bounce
        if "\n\n" in text:
            body_only = text.split("\n\n", 1)[1]
            if self._fingerprint(sender, body_only) in self._recent_fingerprints:
                return True
        return False

    def mark_outbound(self, recipient: str, text: str) -> None:
        self._gc_recent()
        self._recent_fingerprints[self._fingerprint(recipient, text)] = time.time()
        if self.signature:
            # Also fingerprint text+signature so bounced replies are detected
            self._recent_fingerprints[self._fingerprint(recipient, text + self.signature)] = time.time()
