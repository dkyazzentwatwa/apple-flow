from __future__ import annotations

import argparse
import asyncio
import atexit
import fcntl
from pathlib import Path
import sys

import uvicorn

from .config import RelaySettings
from .daemon import run as run_daemon

_LOCK_FILE = None


def _acquire_daemon_lock() -> tuple[int, Path]:
    settings = RelaySettings()
    lock_path = Path(settings.db_path).with_suffix(".daemon.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = lock_path.open("w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(
            f"Another Apple Flow daemon appears to be running (lock: {lock_path})."
        ) from exc
    lock_fd.write(str(Path.cwd()))
    lock_fd.flush()
    global _LOCK_FILE
    _LOCK_FILE = lock_fd
    atexit.register(lock_fd.close)
    return lock_fd.fileno(), lock_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Apple Flow runtime")
    parser.add_argument("mode", choices=["daemon", "admin"], nargs="?", default="daemon")
    args = parser.parse_args()

    if args.mode == "daemon":
        try:
            _acquire_daemon_lock()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        asyncio.run(run_daemon())
        return

    settings = RelaySettings()
    uvicorn.run("apple_flow.main:app", host=settings.admin_host, port=settings.admin_port, reload=False)


if __name__ == "__main__":
    main()
