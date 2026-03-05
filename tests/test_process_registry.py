from __future__ import annotations

import subprocess
import time

from apple_flow.process_registry import ManagedProcessRegistry


def test_reap_orphans_kills_persisted_process(tmp_path):
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        registry_a = ManagedProcessRegistry("codex-cli-test", state_dir=tmp_path)
        registry_a.register("sender_a", proc)

        registry_b = ManagedProcessRegistry("codex-cli-test", state_dir=tmp_path)
        killed = registry_b.reap_orphans()

        assert killed == 1
        proc.wait(timeout=2)
    finally:
        if proc.poll() is None:
            proc.kill()


def test_cancel_kills_persisted_process_for_matching_thread(tmp_path):
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        registry_a = ManagedProcessRegistry("codex-cli-test-thread", state_dir=tmp_path)
        registry_a.register("sender_a", proc)

        registry_b = ManagedProcessRegistry("codex-cli-test-thread", state_dir=tmp_path)
        killed = registry_b.cancel("sender_a")

        assert killed == 1
        proc.wait(timeout=2)
    finally:
        if proc.poll() is None:
            proc.kill()
