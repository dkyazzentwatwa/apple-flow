from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from tempfile import gettempdir

logger = logging.getLogger("apple_flow.process_registry")


class ManagedProcessRegistry:
    """Track active connector subprocesses and support emergency cancellation."""

    def __init__(self, label: str, state_dir: str | Path | None = None) -> None:
        self.label = label
        self._lock = threading.Lock()
        self._entries: dict[int, tuple[str, subprocess.Popen[str]]] = {}
        base_dir = Path(state_dir) if state_dir is not None else Path(gettempdir()) / "apple-flow-process-registry"
        self._registry_path = base_dir / f"{self.label}.json"
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._prune_persisted_entries()

    def register(self, thread_id: str, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            self._entries[int(proc.pid)] = (thread_id, proc)
            self._persist_locked()

    def unregister(self, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            self._entries.pop(int(proc.pid), None)
            self._persist_locked()

    def cancel(self, thread_id: str | None = None) -> int:
        with self._lock:
            live_targets = [
                proc for tid, proc in self._entries.values()
                if thread_id is None or tid == thread_id
            ]
            persisted = self._read_registry_locked()
            persisted_targets = [
                int(pid_str) for pid_str, tid in persisted.items()
                if thread_id is None or tid == thread_id
            ]
        killed = 0
        for proc in live_targets:
            if self.terminate(proc):
                killed += 1
        for pid in persisted_targets:
            if self._terminate_pid(pid):
                killed += 1
        self._prune_persisted_entries()
        return killed

    def reap_orphans(self) -> int:
        with self._lock:
            persisted_targets = [int(pid_str) for pid_str in self._read_registry_locked().keys()]
        killed = 0
        for pid in persisted_targets:
            if self._terminate_pid(pid):
                killed += 1
        self._prune_persisted_entries()
        return killed

    def terminate(self, proc: subprocess.Popen[str], grace_seconds: float = 0.35) -> bool:
        """Terminate a process group, escalating to SIGKILL if needed."""
        pid = int(proc.pid)
        if proc.poll() is not None:
            self._remove_pid(pid)
            return False

        terminated = self._terminate_pid(pid, grace_seconds=grace_seconds)
        self._remove_pid(pid)
        return terminated

    def _terminate_pid(self, pid: int, grace_seconds: float = 0.35) -> bool:
        terminated = False
        try:
            # start_new_session=True makes pid the process-group id.
            os.killpg(pid, signal.SIGTERM)
            terminated = True
        except ProcessLookupError:
            self._remove_pid(pid)
            return False
        except Exception:
            # Fallback for environments where process-group signaling is unavailable.
            try:
                os.kill(pid, signal.SIGTERM)
                terminated = True
            except Exception:
                logger.debug("Failed SIGTERM for %s pid=%s", self.label, pid, exc_info=True)
                return False

        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            if not self._pid_exists(pid):
                self._remove_pid(pid)
                return terminated
            time.sleep(0.02)

        if not self._pid_exists(pid):
            self._remove_pid(pid)
            return terminated

        try:
            os.killpg(pid, signal.SIGKILL)
            self._remove_pid(pid)
            return True
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
                self._remove_pid(pid)
                return True
            except Exception:
                logger.debug("Failed SIGKILL for %s pid=%s", self.label, pid, exc_info=True)
                return terminated

    def _pid_exists(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return True

    def _remove_pid(self, pid: int) -> None:
        with self._lock:
            if pid in self._entries:
                self._entries.pop(pid, None)
            persisted = self._read_registry_locked()
            if str(pid) in persisted:
                persisted.pop(str(pid), None)
                self._write_registry_locked(persisted)

    def _prune_persisted_entries(self) -> None:
        with self._lock:
            persisted = self._read_registry_locked()
            active = {pid_str: tid for pid_str, tid in persisted.items() if self._pid_exists(int(pid_str))}
            live = {str(pid): tid for pid, (tid, _proc) in self._entries.items()}
            merged = {**active, **live}
            self._write_registry_locked(merged)

    def _persist_locked(self) -> None:
        persisted = self._read_registry_locked()
        live = {str(pid): tid for pid, (tid, _proc) in self._entries.items()}
        persisted.update(live)
        self._write_registry_locked(persisted)

    def _read_registry_locked(self) -> dict[str, str]:
        try:
            if not self._registry_path.exists():
                return {}
            raw = json.loads(self._registry_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            entries = raw.get("entries", raw)
            if not isinstance(entries, dict):
                return {}
            out: dict[str, str] = {}
            for pid_str, thread_id in entries.items():
                if str(pid_str).isdigit():
                    out[str(pid_str)] = str(thread_id)
            return out
        except Exception:
            logger.debug("Failed reading registry for %s", self.label, exc_info=True)
            return {}

    def _write_registry_locked(self, entries: dict[str, str]) -> None:
        try:
            if not entries:
                self._registry_path.unlink(missing_ok=True)
                return
            payload = {"entries": entries}
            self._registry_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        except Exception:
            logger.debug("Failed writing registry for %s", self.label, exc_info=True)
