from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import time
from pathlib import Path

from .apple_tools import _send_imessage_attachment

from .utils import normalize_echo_text, normalize_sender

logger = logging.getLogger("apple_flow.egress")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif", ".tiff", ".bmp"}


class IMessageEgress:
    def __init__(
        self,
        max_chunk_chars: int = 1200,
        retries: int = 3,
        echo_window_seconds: float = 180.0,
        suppress_duplicate_outbound_seconds: float = 90.0,
        auto_send_image_results: str = "off",
        image_result_owner_number: str = "",
        image_result_max_attachments: int = 3,
    ):
        self.max_chunk_chars = max_chunk_chars
        self.retries = retries
        self.echo_window_seconds = echo_window_seconds
        self.suppress_duplicate_outbound_seconds = suppress_duplicate_outbound_seconds
        self.auto_send_image_results = self._normalize_auto_send_mode(auto_send_image_results)
        self.image_result_owner_number = normalize_sender(image_result_owner_number)
        self.image_result_max_attachments = max(1, int(image_result_max_attachments))
        self._recent_fingerprints: dict[str, float] = {}
        self._recent_normalized_texts: dict[tuple[str, str], float] = {}
        self._recent_attachment_recipients: dict[str, float] = {}

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
        # Escape backslashes first, then quotes, then newlines
        escaped_text = (
            text.replace('\\', '\\\\')
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "")
        )
        script = f'''
        tell application "Messages"
            set targetService to 1st service whose service type = iMessage
            set targetBuddy to buddy "{recipient}" of targetService
            send "{escaped_text}" to targetBuddy
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

    @staticmethod
    def _normalize_auto_send_mode(value: str) -> str:
        normalized = (value or "off").strip().lower()
        allowed = {"off", "owner-only", "allowed-senders"}
        if normalized in allowed:
            return normalized
        raise ValueError(
            f"Invalid auto_send_image_results {value!r}. Allowed: {', '.join(sorted(allowed))}"
        )

    def _gc_recent(self) -> None:
        now = time.time()
        expired_fingerprints = [
            fingerprint
            for fingerprint, ts in self._recent_fingerprints.items()
            if (now - ts) > self.echo_window_seconds
        ]
        for fingerprint in expired_fingerprints:
            self._recent_fingerprints.pop(fingerprint, None)
        expired_texts = [
            key
            for key, ts in self._recent_normalized_texts.items()
            if (now - ts) > self.echo_window_seconds
        ]
        for key in expired_texts:
            self._recent_normalized_texts.pop(key, None)
        expired_attachments = [
            recipient
            for recipient, ts in self._recent_attachment_recipients.items()
            if (now - ts) > self.echo_window_seconds
        ]
        for recipient in expired_attachments:
            self._recent_attachment_recipients.pop(recipient, None)

    def was_recent_outbound(self, sender: str, text: str) -> bool:
        self._gc_recent()
        if self._fingerprint(sender, text) in self._recent_fingerprints:
            return True

        normalized_sender = normalize_sender(sender)
        normalized_text = normalize_echo_text(text)
        if not normalized_text:
            return False
        if (normalized_sender, normalized_text) in self._recent_normalized_texts:
            return True
        # attributedBody fallback can drop leading chars or return mid-run fragments.
        # Use containment only for long snippets to avoid false positives on short text.
        if len(normalized_text) < 40:
            return False
        for (candidate_sender, candidate_text), _ in self._recent_normalized_texts.items():
            if candidate_sender != normalized_sender:
                continue
            if normalized_text in candidate_text or candidate_text in normalized_text:
                return True
        return False

    def mark_outbound(self, recipient: str, text: str) -> None:
        self._gc_recent()
        now = time.time()
        self._recent_fingerprints[self._fingerprint(recipient, text)] = now
        normalized_sender = normalize_sender(recipient)
        normalized_text = normalize_echo_text(text)
        if normalized_text:
            self._recent_normalized_texts[(normalized_sender, normalized_text)] = now

    def mark_attachment_outbound(self, recipient: str) -> None:
        self._gc_recent()
        self._recent_attachment_recipients[normalize_sender(recipient)] = time.time()

    def was_recent_attachment_outbound(self, sender: str) -> bool:
        self._gc_recent()
        return normalize_sender(sender) in self._recent_attachment_recipients

    def _should_auto_send_image_results(self, recipient: str) -> bool:
        if self.auto_send_image_results == "off":
            return False
        if self.auto_send_image_results == "allowed-senders":
            return True
        if self.auto_send_image_results == "owner-only":
            return bool(self.image_result_owner_number) and normalize_sender(recipient) == self.image_result_owner_number
        return False

    @staticmethod
    def _extract_markdown_image_path(stripped: str) -> str | None:
        match = re.fullmatch(r"!\[[^\]]*\]\((/[^)]+)\)", stripped)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _extract_markdown_link_image_path(stripped: str) -> str | None:
        if "[" not in stripped or "](" not in stripped:
            return None
        match = re.fullmatch(r"(?:[^:\n]+:\s+)?\[[^\]]+\]\((/[^)]+)\)", stripped)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _extract_labeled_image_path(stripped: str) -> str | None:
        if ":" not in stripped:
            return None
        _label, candidate = stripped.split(":", 1)
        candidate = candidate.strip()
        if candidate.startswith("/"):
            return candidate
        return None

    @staticmethod
    def _resolve_image_path(candidate: str | None) -> Path | None:
        if not candidate:
            return None
        if not candidate.startswith("/"):
            return None
        path = Path(candidate)
        if path.suffix.lower() not in _IMAGE_SUFFIXES:
            return None
        if not path.exists() or not path.is_file():
            return None
        return path

    def _extract_image_candidates(self, text: str) -> list[tuple[int, Path]]:
        candidates: list[tuple[int, Path]] = []
        in_code_fence = False
        for idx, raw_line in enumerate(text.splitlines()):
            stripped = raw_line.strip()
            if stripped.startswith("```"):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence or not stripped:
                continue

            candidate = stripped if stripped.startswith("/") else self._extract_labeled_image_path(stripped)
            if candidate is None:
                candidate = self._extract_markdown_image_path(stripped)
            if candidate is None:
                candidate = self._extract_markdown_link_image_path(stripped)

            path = self._resolve_image_path(candidate)
            if path is None:
                continue
            candidates.append((idx, path))
        return candidates

    @staticmethod
    def _cleanup_text_after_image_removal(text: str, removed_indexes: set[int]) -> str:
        lines = [line for idx, line in enumerate(text.splitlines()) if idx not in removed_indexes]
        cleaned = "\n".join(lines).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned

    def _maybe_prepare_image_result_text(self, recipient: str, text: str) -> str | None:
        if not self._should_auto_send_image_results(recipient):
            return None

        candidates = self._extract_image_candidates(text)
        if not candidates:
            return None

        sent_count = 0
        for _idx, path in candidates[: self.image_result_max_attachments]:
            result = _send_imessage_attachment(recipient, str(path))
            if result.get("ok"):
                sent_count += 1

        if sent_count == 0:
            return None

        self.mark_attachment_outbound(recipient)
        removed_indexes = {idx for idx, _path in candidates}
        cleaned = self._cleanup_text_after_image_removal(text, removed_indexes)
        total_candidates = len(candidates)
        if cleaned:
            if sent_count == total_candidates:
                return cleaned
            plural = "image" if sent_count == 1 else "images"
            return f"{cleaned}\n\nAttached {sent_count} of {total_candidates} {plural}."

        if sent_count == total_candidates:
            return "Attached image." if sent_count == 1 else f"Attached {sent_count} images."
        plural = "image" if sent_count == 1 else "images"
        return f"Attached {sent_count} of {total_candidates} {plural}."

    def _send_text_chunks(self, recipient: str, text: str) -> None:
        logger.info("Sending iMessage to %s (%s chars)", recipient, len(text))
        chunks = self._chunk(text)
        for chunk in chunks:
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
        if len(chunks) > 1:
            # Messages can store chunked sends as one merged bubble in chat.db.
            # Keep a full-text marker so inbound echo checks match either shape.
            self.mark_outbound(recipient, text)

    def send(self, recipient: str, text: str, context: dict | None = None) -> None:
        self._gc_recent()
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

        outbound_text = self._maybe_prepare_image_result_text(recipient, text) or text
        self._send_text_chunks(recipient, outbound_text)
        if outbound_text != text:
            self.mark_outbound(recipient, text)
