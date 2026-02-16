from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import time

from .utils import normalize_sender

logger = logging.getLogger("codex_relay.egress")


class IMessageEgress:
    def __init__(
        self,
        max_chunk_chars: int = 1200,
        retries: int = 3,
        echo_window_seconds: float = 180.0,
        suppress_duplicate_outbound_seconds: float = 90.0,
    ):
        self.max_chunk_chars = max_chunk_chars
        self.retries = retries
        self.echo_window_seconds = echo_window_seconds
        self.suppress_duplicate_outbound_seconds = suppress_duplicate_outbound_seconds
        self._recent_fingerprints: dict[str, float] = {}

    def _chunk(self, text: str) -> list[str]:
        if len(text) <= self.max_chunk_chars:
            return [text]
        chunks = []
        remaining = text
        while remaining:
            chunks.append(remaining[: self.max_chunk_chars])
            remaining = remaining[self.max_chunk_chars :]
        return chunks

    @staticmethod
    def _osascript_send(recipient: str, text: str) -> None:
        script = f'''
        tell application "Messages"
            set targetService to 1st service whose service type = iMessage
            set targetBuddy to buddy "{recipient}" of targetService
            send "{text.replace('"', '\\"')}" to targetBuddy
        end tell
        '''
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)

    def _fingerprint(self, handle: str, text: str) -> str:
        normalized = normalize_sender(handle)
        normalized_text = self._normalize_text(text)
        payload = f"{normalized}:{normalized_text}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = (text or "").replace("\u2019", "'").replace("\u2018", "'")
        cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
        return cleaned

    def _gc_recent(self) -> None:
        now = time.time()
        expired = [
            fingerprint
            for fingerprint, ts in self._recent_fingerprints.items()
            if (now - ts) > self.echo_window_seconds
        ]
        for fingerprint in expired:
            self._recent_fingerprints.pop(fingerprint, None)

    def was_recent_outbound(self, sender: str, text: str) -> bool:
        self._gc_recent()
        return self._fingerprint(sender, text) in self._recent_fingerprints

    def mark_outbound(self, recipient: str, text: str) -> None:
        self._gc_recent()
        self._recent_fingerprints[self._fingerprint(recipient, text)] = time.time()

    def send(self, recipient: str, text: str) -> None:
        outbound_fingerprint = self._fingerprint(recipient, text)
        last_ts = self._recent_fingerprints.get(outbound_fingerprint)
        if last_ts is not None and (time.time() - last_ts) <= self.suppress_duplicate_outbound_seconds:
            logger.info(
                "Suppressing duplicate outbound message to %s (%s chars) within %.1fs window",
                recipient,
                len(text),
                self.suppress_duplicate_outbound_seconds,
            )
            return

        logger.info("Sending iMessage to %s (%s chars)", recipient, len(text))
        for chunk in self._chunk(text):
            last_error: Exception | None = None
            for attempt in range(1, self.retries + 1):
                try:
                    self._osascript_send(recipient, chunk)
                    self.mark_outbound(recipient, chunk)
                    logger.info("Sent chunk to %s (%s chars)", recipient, len(chunk))
                    last_error = None
                    break
                except Exception as exc:  # pragma: no cover - depends on macOS runtime
                    last_error = exc
                    logger.warning("Send retry %s failed for %s: %s", attempt, recipient, exc)
                    time.sleep(0.25 * attempt)
            if last_error is not None:
                raise RuntimeError(f"Failed to send iMessage after retries: {last_error}") from last_error
