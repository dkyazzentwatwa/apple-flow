"""Tests for egress message chunking and retry logic."""


from apple_flow.egress import IMessageEgress


def test_chunk_short_message():
    """Short messages should not be chunked."""
    egress = IMessageEgress(max_chunk_chars=100)
    chunks = egress._chunk("Hello world")
    assert len(chunks) == 1
    assert chunks[0] == "Hello world"


def test_chunk_exactly_max_length():
    """Message at exactly max length should not be chunked."""
    egress = IMessageEgress(max_chunk_chars=10)
    text = "0123456789"  # exactly 10 chars
    chunks = egress._chunk(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_long_message():
    """Long messages should be chunked."""
    egress = IMessageEgress(max_chunk_chars=10)
    text = "0123456789ABCDEFGHIJ"  # 20 chars
    chunks = egress._chunk(text)
    assert len(chunks) == 2
    assert chunks[0] == "0123456789"
    assert chunks[1] == "ABCDEFGHIJ"


def test_chunk_uneven_split():
    """Uneven splits should work correctly."""
    egress = IMessageEgress(max_chunk_chars=10)
    text = "0123456789ABC"  # 13 chars
    chunks = egress._chunk(text)
    assert len(chunks) == 2
    assert chunks[0] == "0123456789"
    assert chunks[1] == "ABC"


def test_fingerprint_normalization():
    """Fingerprints should normalize handles and text."""
    egress = IMessageEgress()

    # Same message, different handle formats
    fp1 = egress._fingerprint("+15551234567", "Hello")
    fp2 = egress._fingerprint("15551234567", "Hello")
    assert fp1 == fp2

    # Different messages should have different fingerprints
    fp3 = egress._fingerprint("+15551234567", "Goodbye")
    assert fp1 != fp3


def test_text_normalization():
    """Text normalization should handle whitespace and quotes."""
    egress = IMessageEgress()

    # Whitespace normalization
    normalized1 = egress._normalize_text("  hello   world  ")
    assert normalized1 == "hello world"

    # Smart quote normalization
    normalized2 = egress._normalize_text("it's")
    assert "'" in normalized2


def test_duplicate_suppression():
    """Duplicate outbound messages should be suppressed."""
    egress = IMessageEgress(suppress_duplicate_outbound_seconds=60.0)

    # First send should not be suppressed
    egress.mark_outbound("+15551234567", "Test message")
    assert egress.was_recent_outbound("+15551234567", "Test message")

    # Different message should not be marked as recent
    assert not egress.was_recent_outbound("+15551234567", "Different message")

    # Different recipient should not be marked as recent
    assert not egress.was_recent_outbound("+15559999999", "Test message")


def test_gc_recent_clears_old_fingerprints():
    """Garbage collection should clear old fingerprints."""
    egress = IMessageEgress(echo_window_seconds=0.0)  # Immediate expiry

    egress.mark_outbound("+15551234567", "Test")
    egress._gc_recent()

    # Should be cleared due to 0 second window
    assert not egress.was_recent_outbound("+15551234567", "Test")
