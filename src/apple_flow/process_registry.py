from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time

logger = logging.getLogger("apple_flow.process_registry")


class ManagedProcessRegistry:
    """Track active connector subprocesses and support emergency cancellation."""

    def __init__(self, label: str) -> None:
        self.label = label
        self._lock = threading.Lock()
        self._entries: dict[int, tuple[str, subprocess.Popen[str]]] = {}

    def register(self, thread_id: str, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            self._entries[int(proc.pid)] = (thread_id, proc)

    def unregister(self, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            self._entries.pop(int(proc.pid), None)

    def cancel(self, thread_id: str | None = None) -> int:
        with self._lock:
            targets = [
                proc
                for tid, proc in self._entries.values()
                if thread_id is None or tid == thread_id
            ]
        killed = 0
        for proc in targets:
            if self.terminate(proc):
                killed += 1
        return killed

    def terminate(self, proc: subprocess.Popen[str], grace_seconds: float = 0.35) -> bool:
        """Terminate a process group, escalating to SIGKILL if needed."""
        pid = int(proc.pid)
        if proc.poll() is not None:
            return False

        terminated = False
        try:
            # start_new_session=True makes pid the process-group id.
            os.killpg(pid, signal.SIGTERM)
            terminated = True
        except ProcessLookupError:
            return False
        except Exception:
            # Fallback for environments where process-group signaling is unavailable.
            try:
                proc.terminate()
                terminated = True
            except Exception:
                logger.debug("Failed SIGTERM for %s pid=%s", self.label, pid, exc_info=True)
                return False

        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return terminated
            time.sleep(0.02)

        if proc.poll() is not None:
            return terminated

        try:
            os.killpg(pid, signal.SIGKILL)
            return True
        except Exception:
            try:
                proc.kill()
                return True
            except Exception:
                logger.debug("Failed SIGKILL for %s pid=%s", self.label, pid, exc_info=True)
                return terminated
