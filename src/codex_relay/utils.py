"""Shared utility functions for Codex Relay."""

from __future__ import annotations


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
