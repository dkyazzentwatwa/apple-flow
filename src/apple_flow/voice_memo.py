"""Generates voice memos from text using macOS native TTS.

Uses the `say` command for text-to-speech and `afconvert` to convert
the output to an iMessage-friendly M4A (AAC) format.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("apple_flow.voice_memo")


def generate_voice_memo(
    text: str,
    output_dir: str = "/tmp/apple_flow_attachments",
    voice: str = "Samantha",
    max_chars: int = 2000,
) -> str | None:
    """Convert text to a voice memo M4A file.

    Uses macOS `say` to generate AIFF, then `afconvert` to M4A (AAC).

    Args:
        text: The text to convert to speech.
        output_dir: Directory to store the generated audio file.
        voice: macOS TTS voice name (default: Samantha).
        max_chars: Maximum characters to convert (truncates with notice).

    Returns:
        Absolute path to the generated M4A file, or None on failure.
    """
    if not text or not text.strip():
        logger.warning("Empty text, skipping voice memo generation")
        return None

    # Truncate if needed
    clean_text = text.strip()
    if len(clean_text) > max_chars:
        clean_text = clean_text[:max_chars] + "... (response truncated for voice memo)"

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Create temp files for intermediate AIFF and final M4A
    aiff_fd, aiff_path = tempfile.mkstemp(suffix=".aiff", dir=output_dir, prefix="codex_memo_")
    os.close(aiff_fd)

    m4a_path = aiff_path.replace(".aiff", ".m4a")

    try:
        # Step 1: Generate AIFF with `say`
        say_cmd = ["say", "-v", voice, "-o", aiff_path]
        result = subprocess.run(
            say_cmd,
            input=clean_text,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            # Try fallback voice if specified voice not available
            logger.warning(
                "say failed with voice %r (rc=%d): %s. Trying default voice.",
                voice, result.returncode, result.stderr.strip(),
            )
            say_cmd = ["say", "-o", aiff_path]
            result = subprocess.run(
                say_cmd,
                input=clean_text,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.error("say command failed (rc=%d): %s", result.returncode, result.stderr.strip())
                _cleanup(aiff_path)
                return None

        if not Path(aiff_path).exists() or Path(aiff_path).stat().st_size == 0:
            logger.error("say produced empty or missing AIFF file")
            _cleanup(aiff_path)
            return None

        # Step 2: Convert AIFF to M4A (AAC) with `afconvert`
        convert_cmd = [
            "afconvert",
            aiff_path,
            m4a_path,
            "-f", "m4af",
            "-d", "aac",
        ]
        result = subprocess.run(
            convert_cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.error("afconvert failed (rc=%d): %s", result.returncode, result.stderr.strip())
            _cleanup(aiff_path)
            return None

        if not Path(m4a_path).exists() or Path(m4a_path).stat().st_size == 0:
            logger.error("afconvert produced empty or missing M4A file")
            _cleanup(aiff_path, m4a_path)
            return None

        # Clean up intermediate AIFF
        _cleanup(aiff_path)

        logger.info(
            "Generated voice memo: %s (%d bytes, %d chars of text)",
            m4a_path, Path(m4a_path).stat().st_size, len(clean_text),
        )
        return m4a_path

    except subprocess.TimeoutExpired:
        logger.error("Voice memo generation timed out")
        _cleanup(aiff_path, m4a_path)
        return None
    except FileNotFoundError as exc:
        logger.error("Required command not found: %s (voice memos require macOS)", exc)
        _cleanup(aiff_path, m4a_path)
        return None
    except Exception as exc:
        logger.error("Unexpected error generating voice memo: %s", exc)
        _cleanup(aiff_path, m4a_path)
        return None


def cleanup_voice_memo(file_path: str) -> None:
    """Remove a voice memo file after it has been sent."""
    _cleanup(file_path)


def _cleanup(*paths: str) -> None:
    """Safely remove files, ignoring errors."""
    for path in paths:
        try:
            if path and Path(path).exists():
                Path(path).unlink()
        except OSError:
            pass
