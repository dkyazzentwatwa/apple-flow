"""Tests for voice memo generation and orchestrator integration."""

import os
import tempfile
from unittest.mock import patch, MagicMock, call
from dataclasses import dataclass, field

from apple_flow.commanding import CommandKind
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator
from apple_flow.voice_memo import generate_voice_memo, cleanup_voice_memo

from conftest import FakeConnector, FakeStore


# --- FakeEgress with send_attachment ---


class FakeEgressWithAttachment:
    """Fake egress that tracks both text sends and attachment sends."""

    def __init__(self):
        self.messages: list[tuple[str, str]] = []
        self.attachments: list[tuple[str, str]] = []

    def send(self, recipient: str, text: str) -> None:
        self.messages.append((recipient, text))

    def send_attachment(self, recipient: str, file_path: str) -> None:
        self.attachments.append((recipient, file_path))

    def was_recent_outbound(self, sender: str, text: str) -> bool:
        return False

    def mark_outbound(self, recipient: str, text: str) -> None:
        pass


# --- generate_voice_memo Unit Tests ---


@patch("apple_flow.voice_memo.subprocess.run")
def test_generate_voice_memo_success(mock_run):
    """Test successful voice memo generation with say + afconvert."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock say to create a fake AIFF file
        def side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            if cmd[0] == "say":
                # Create a fake AIFF file
                output_path = cmd[cmd.index("-o") + 1]
                with open(output_path, "wb") as f:
                    f.write(b"fake aiff data")
            elif cmd[0] == "afconvert":
                # Create a fake M4A file
                output_path = cmd[2]
                with open(output_path, "wb") as f:
                    f.write(b"fake m4a data")
            return result

        mock_run.side_effect = side_effect

        path = generate_voice_memo("Hello world", output_dir=tmpdir)
        assert path is not None
        assert path.endswith(".m4a")
        assert mock_run.call_count == 2


@patch("apple_flow.voice_memo.subprocess.run")
def test_generate_voice_memo_empty_text(mock_run):
    """Empty text returns None without calling subprocess."""
    result = generate_voice_memo("")
    assert result is None
    mock_run.assert_not_called()


@patch("apple_flow.voice_memo.subprocess.run")
def test_generate_voice_memo_say_fails_with_fallback(mock_run):
    """When say fails with specified voice, tries default voice."""
    with tempfile.TemporaryDirectory() as tmpdir:
        call_count = [0]

        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            result.stderr = "voice not found"

            if cmd[0] == "say" and "-v" in cmd:
                # First say with voice fails
                result.returncode = 1
                return result
            elif cmd[0] == "say":
                # Second say without voice succeeds
                result.returncode = 0
                output_path = cmd[cmd.index("-o") + 1]
                with open(output_path, "wb") as f:
                    f.write(b"fake aiff data")
                return result
            elif cmd[0] == "afconvert":
                result.returncode = 0
                output_path = cmd[2]
                with open(output_path, "wb") as f:
                    f.write(b"fake m4a data")
                return result

        mock_run.side_effect = side_effect

        path = generate_voice_memo("Hello", output_dir=tmpdir, voice="NonExistentVoice")
        assert path is not None
        assert call_count[0] == 3  # say(voice), say(default), afconvert


@patch("apple_flow.voice_memo.subprocess.run")
def test_generate_voice_memo_say_completely_fails(mock_run):
    """When both say attempts fail, returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = MagicMock()
        result.returncode = 1
        result.stderr = "say error"
        mock_run.return_value = result

        path = generate_voice_memo("Hello", output_dir=tmpdir)
        assert path is None


@patch("apple_flow.voice_memo.subprocess.run")
def test_generate_voice_memo_timeout(mock_run):
    """Timeout returns None."""
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="say", timeout=120)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = generate_voice_memo("Hello", output_dir=tmpdir)
        assert path is None


@patch("apple_flow.voice_memo.subprocess.run")
def test_generate_voice_memo_not_found(mock_run):
    """FileNotFoundError (no macOS) returns None."""
    mock_run.side_effect = FileNotFoundError("say not found")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = generate_voice_memo("Hello", output_dir=tmpdir)
        assert path is None


def test_generate_voice_memo_truncates_long_text():
    """Text longer than max_chars gets truncated."""
    with patch("apple_flow.voice_memo.subprocess.run") as mock_run:
        with tempfile.TemporaryDirectory() as tmpdir:
            def side_effect(cmd, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stderr = ""
                if cmd[0] == "say":
                    # Check the input text was truncated
                    input_text = kwargs.get("input", "")
                    assert len(input_text) < 100  # Original was 100 chars, should be truncated
                    output_path = cmd[cmd.index("-o") + 1]
                    with open(output_path, "wb") as f:
                        f.write(b"fake aiff data")
                elif cmd[0] == "afconvert":
                    output_path = cmd[2]
                    with open(output_path, "wb") as f:
                        f.write(b"fake m4a data")
                return result

            mock_run.side_effect = side_effect
            path = generate_voice_memo("A" * 100, output_dir=tmpdir, max_chars=50)
            assert path is not None


def test_cleanup_voice_memo():
    """Cleanup removes the file."""
    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
        f.write(b"test data")
        path = f.name

    assert os.path.exists(path)
    cleanup_voice_memo(path)
    assert not os.path.exists(path)


def test_cleanup_voice_memo_missing_file():
    """Cleanup handles missing file gracefully."""
    cleanup_voice_memo("/nonexistent/path/file.m4a")  # Should not raise


# --- Orchestrator Integration Tests ---


def _make_orchestrator(
    enable_voice=True,
    send_text_too=True,
    egress=None,
):
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=egress or FakeEgressWithAttachment(),
        store=FakeStore(),
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
        enable_voice_memos=enable_voice,
        voice_memo_voice="Samantha",
        voice_memo_max_chars=2000,
        voice_memo_send_text_too=send_text_too,
        voice_memo_output_dir="/tmp/test_voice_memos",
    )


def _msg(text, sender="+15551234567", msg_id="m1"):
    return InboundMessage(
        id=msg_id, sender=sender, text=text,
        received_at="2026-02-17T12:00:00Z", is_from_me=False,
    )


@patch("apple_flow.orchestrator.generate_voice_memo")
def test_voice_memo_sent_with_text_response(mock_gen):
    mock_gen.return_value = "/tmp/memo.m4a"
    orch = _make_orchestrator(enable_voice=True, send_text_too=True)

    result = orch.handle_message(_msg("idea: brainstorm features"))
    assert result.kind is CommandKind.IDEA

    # Text was sent
    assert len(orch.egress.messages) > 0
    # Attachment was sent
    assert len(orch.egress.attachments) == 1
    assert orch.egress.attachments[0] == ("+15551234567", "/tmp/memo.m4a")


@patch("apple_flow.orchestrator.generate_voice_memo")
def test_voice_memo_only_no_text(mock_gen):
    mock_gen.return_value = "/tmp/memo.m4a"
    orch = _make_orchestrator(enable_voice=True, send_text_too=False)

    orch.handle_message(_msg("idea: brainstorm features"))

    # Text was NOT sent (voice_memo_send_text_too=False)
    assert len(orch.egress.messages) == 0
    # Attachment was sent
    assert len(orch.egress.attachments) == 1


@patch("apple_flow.orchestrator.generate_voice_memo")
def test_voice_memo_disabled(mock_gen):
    orch = _make_orchestrator(enable_voice=False)

    orch.handle_message(_msg("idea: brainstorm features"))

    # Text was sent but no voice memo
    assert len(orch.egress.messages) > 0
    assert len(orch.egress.attachments) == 0
    mock_gen.assert_not_called()


@patch("apple_flow.orchestrator.generate_voice_memo")
def test_voice_memo_generation_fails_gracefully(mock_gen):
    mock_gen.return_value = None  # Generation failed
    orch = _make_orchestrator(enable_voice=True, send_text_too=True)

    result = orch.handle_message(_msg("idea: brainstorm features"))

    # Text still sent even if voice memo fails
    assert len(orch.egress.messages) > 0
    assert len(orch.egress.attachments) == 0  # Nothing to attach


@patch("apple_flow.orchestrator.cleanup_voice_memo")
@patch("apple_flow.orchestrator.generate_voice_memo")
def test_voice_memo_cleaned_up_after_send(mock_gen, mock_cleanup):
    mock_gen.return_value = "/tmp/memo.m4a"
    orch = _make_orchestrator(enable_voice=True)

    orch.handle_message(_msg("idea: brainstorm features"))

    # Cleanup was called
    mock_cleanup.assert_called_once_with("/tmp/memo.m4a")
