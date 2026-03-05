"""Shared utility functions for Apple Flow."""

from __future__ import annotations

import re


def normalize_sender(raw: str) -> str:
    """Normalize a sender handle to a canonical format.

    - Strips whitespace
    - Removes mailto: prefix
    - Converts phone numbers to E.164 format (+digits)

    Args:
        raw: The raw sender handle string (phone number or email)

    Returns:
        Normalized sender string
    """
    sender = (raw or "").strip()
    if sender.startswith("mailto:"):
        sender = sender[7:]
    if sender.startswith("+"):
        return sender
    digits = "".join(ch for ch in sender if ch.isdigit())
    if len(digits) >= 10:
        return f"+{digits}"
    return sender


def normalize_echo_text(text: str) -> str:
    """Normalize message text for durable echo-suppression matching.

    This intentionally tolerates punctuation/emoji drift introduced by
    attributedBody decoding by collapsing punctuation into whitespace and
    normalizing quote variants.
    """
    normalized = (text or "")
    normalized = normalized.replace("\u2019", "'").replace("\u2018", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    normalized = normalized.replace('"', "'").lower()
    normalized = re.sub(r"[^a-z0-9@:+#./'_-]+", " ", normalized)
    return " ".join(normalized.split())
