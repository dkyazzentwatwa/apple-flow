from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import snapshot


def _build_workspace_snapshot(workspace: Path) -> dict[str, Any]:
    """Build a minimal workspace snapshot for dashboard consumers."""
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workspace": {"name": workspace.name, "path": str(workspace)},
        "logs": snapshot._log_stats(workspace),
    }


class DashboardHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        workspace_path: Path,
        links: list[dict[str, str]] | None = None,
        snapshot_ttl_seconds: int = 30,
    ) -> None:
        super().__init__(server_address, DashboardHandler)
        self.workspace_path = workspace_path
        self.links = links or []
        self.snapshot_ttl_seconds = snapshot_ttl_seconds
        self._snapshot_cache: dict[str, Any] | None = None
        self._snapshot_cache_at = 0.0

    def get_snapshot(self) -> dict[str, Any]:
        now = time.time()
        ttl = float(getattr(self, "snapshot_ttl_seconds", 0))
        cache = getattr(self, "_snapshot_cache", None)
        cache_at = float(getattr(self, "_snapshot_cache_at", 0.0))

        if cache is not None and ttl > 0 and (now - cache_at) < ttl:
            return cache

        workspace = Path(getattr(self, "workspace_path"))
        current = _build_workspace_snapshot(workspace)
        self._snapshot_cache = current
        self._snapshot_cache_at = now
        return current


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardHTTPServer

    def _json_response(self, payload: dict[str, Any], status_code: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_workspace_file(self, relative_path: str) -> dict[str, Any]:
        workspace_root = Path(self.server.workspace_path).resolve()
        requested = (workspace_root / relative_path).resolve()

        try:
            requested.relative_to(workspace_root)
        except ValueError:
            return {"ok": False, "error": "path escapes workspace"}

        if not requested.exists():
            return {"ok": False, "error": "file not found"}
        if not requested.is_file():
            return {"ok": False, "error": "path is not a file"}

        return {
            "ok": True,
            "path": str(requested.relative_to(workspace_root)),
            "content": requested.read_text(encoding="utf-8"),
        }

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        if self.path == "/snapshot":
            self._json_response(self.server.get_snapshot(), status_code=200)
            return
        self._json_response({"error": "not found"}, status_code=404)

    def log_message(self, _format: str, *_args: object) -> None:
        """Silence default HTTP request logging in tests."""
        return
