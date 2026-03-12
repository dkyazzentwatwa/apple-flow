"""Runtime gate for coordinating live Reminders UI automation.

This module lets CLI/UI mutation flows briefly pause daemon Reminders polling
to reduce race conditions while AppleScript/Accessibility automations are
interacting with the Reminders UI.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterator

_GATE_FILE_PATH = Path(tempfile.gettempdir()) / "apple-flow-reminders-polling-gate.json"
DEFAULT_GATE_TTL_SECONDS = 300.0
_LOCAL = threading.local()


def _now_epoch() -> float:
    return time.time()


def _write_payload(handle, payload: dict[str, object]) -> None:
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps(payload, sort_keys=True))
    handle.flush()
    os.fsync(handle.fileno())


def _clear_payload(handle) -> None:
    handle.seek(0)
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def _read_payload() -> dict[str, object]:
    if not _GATE_FILE_PATH.exists():
        return {}
    try:
        raw = _GATE_FILE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def is_reminders_polling_paused(now_epoch: float | None = None) -> bool:
    payload = _read_payload()
    if not payload:
        return False
    expires_at_raw = payload.get("expires_at_epoch", 0.0)
    try:
        expires_at = float(expires_at_raw)
    except (TypeError, ValueError):
        return False
    now = _now_epoch() if now_epoch is None else float(now_epoch)
    return expires_at > now


@contextlib.contextmanager
def reminders_live_gate(
    *,
    ttl_seconds: float = DEFAULT_GATE_TTL_SECONDS,
    reason: str = "reminders_live_mutation",
) -> Iterator[None]:
    """Pause daemon Reminders polling while live UI automation is in progress."""
    depth = int(getattr(_LOCAL, "depth", 0))
    if depth > 0:
        _LOCAL.depth = depth + 1
        try:
            yield
        finally:
            _LOCAL.depth = max(0, int(getattr(_LOCAL, "depth", 1)) - 1)
        return

    _GATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = _GATE_FILE_PATH.open("a+", encoding="utf-8")
    _LOCAL.depth = 1
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        now = _now_epoch()
        payload: dict[str, object] = {
            "pid": os.getpid(),
            "reason": reason,
            "created_at_epoch": now,
            "expires_at_epoch": now + max(1.0, float(ttl_seconds)),
        }
        _write_payload(handle, payload)
        yield
    finally:
        try:
            _clear_payload(handle)
        except OSError:
            pass
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            handle.close()
        except OSError:
            pass
        _LOCAL.depth = 0
