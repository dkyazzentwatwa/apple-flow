"""Tests for shared utility functions."""

from apple_flow.utils import normalize_sender


def test_normalize_sender_with_plus():
    """Phone numbers with + should be preserved."""
    assert normalize_sender("+15551234567") == "+15551234567"


def test_normalize_sender_without_plus():
    """Phone numbers without + should get one added."""
    assert normalize_sender("15551234567") == "+15551234567"


def test_normalize_sender_with_formatting():
    """Phone numbers with formatting should be normalized."""
    assert normalize_sender("(555) 123-4567") == "+5551234567"
    assert normalize_sender("555.123.4567") == "+5551234567"


def test_normalize_sender_with_mailto():
    """mailto: prefix should be stripped."""
    assert normalize_sender("mailto:user@example.com") == "user@example.com"


def test_normalize_sender_email():
    """Email addresses should be preserved."""
    assert normalize_sender("user@example.com") == "user@example.com"


def test_normalize_sender_short_number():
    """Short numbers (< 10 digits) should not get + prefix."""
    assert normalize_sender("12345") == "12345"


def test_normalize_sender_whitespace():
    """Whitespace should be stripped."""
    assert normalize_sender("  +15551234567  ") == "+15551234567"


def test_normalize_sender_empty():
    """Empty strings should return empty."""
    assert normalize_sender("") == ""
    assert normalize_sender(None) == ""
