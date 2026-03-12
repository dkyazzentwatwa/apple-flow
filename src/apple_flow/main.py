from __future__ import annotations

import secrets
import sqlite3
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .config import RelaySettings
from .csv_audit import CsvAuditLogger
from .gateway_health import read_all_gateway_health
from .models import InboundMessage
from .runtime_health import read_all_daemon_loop_health, read_daemon_watchdog
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.main")


class ApprovalOverrideBody(BaseModel):
    status: str = Field(pattern="^(approved|denied)$")


class TaskSubmission(BaseModel):
    """Request body for POST /task (Siri Shortcuts / curl bridge)."""
    sender: str = Field(min_length=1)
    text: str = Field(min_length=1)


def _make_auth_dependency(token: str):
    """Create a FastAPI dependency that validates the Authorization: Bearer token."""
    async def _verify_token(request: Request) -> None:
        if not token:
            return  # no token configured — auth disabled
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        provided = auth_header[7:]
        if not secrets.compare_digest(provided, token):
            raise HTTPException(status_code=401, detail="Invalid API token")
    return _verify_token


def build_app(store: Any | None = None) -> FastAPI:
    settings = RelaySettings()
    if store is not None:
        active_store = store
    else:
        csv_audit_logger = None
        if settings.enable_csv_audit_log:
            csv_path = Path(settings.csv_audit_log_path)
            if not csv_path.is_absolute():
                csv_path = Path(__file__).resolve().parents[2] / settings.csv_audit_log_path
            csv_audit_logger = CsvAuditLogger(
                path=csv_path,
                include_headers_if_missing=settings.csv_audit_include_headers_if_missing,
            )
        active_store = SQLiteStore(Path(settings.db_path), csv_audit_logger=csv_audit_logger)
    if hasattr(active_store, "bootstrap"):
        try:
            active_store.bootstrap()
        except sqlite3.OperationalError as exc:
            if store is not None or "readonly" not in str(exc).lower():
                raise
            fallback_db = Path("/tmp/apple-flow-admin-fallback.db")
            logger.warning(
                "Admin API DB path %s is read-only; falling back to %s",
                settings.db_path,
                fallback_db,
            )
            active_store = SQLiteStore(fallback_db)
            active_store.bootstrap()

    verify_token = _make_auth_dependency(settings.admin_api_token)

    app = FastAPI(title="Apple Flow Admin API", version="0.6.0")
    app.state.store = active_store
    # orchestrator is injected by daemon at startup (if running alongside polling)
    app.state.orchestrator = None

    def _runtime_payload() -> dict[str, Any]:
        loops = read_all_daemon_loop_health(app.state.store)
        watchdog = read_daemon_watchdog(app.state.store) or {
            "healthy": True,
            "degraded_reasons": [],
            "last_connector_completion_at": "",
            "oldest_inflight_dispatch_seconds": 0.0,
            "active_helper_count": 0,
            "oldest_helper_age_seconds": 0.0,
            "event_loop_lag_seconds": 0.0,
            "event_loop_lag_failures": 0,
        }
        status = "degraded" if not watchdog.get("healthy", True) else "healthy"
        return {"status": status, "loops": loops, "watchdog": watchdog}

    @app.get("/health")
    def health() -> dict[str, Any]:
        gateways = read_all_gateway_health(app.state.store)
        runtime = _runtime_payload()
        gateway_healthy = all(state.get("healthy", True) for state in gateways.values())
        status = "ok" if gateway_healthy and runtime["status"] == "healthy" else "degraded"
        return {"status": status, "gateways": gateways, "runtime": runtime}

    @app.get("/sessions", dependencies=[Depends(verify_token)])
    def sessions() -> list[dict[str, Any]]:
        return app.state.store.list_sessions()

    @app.get("/runs/{run_id}", dependencies=[Depends(verify_token)])
    def get_run(run_id: str) -> dict[str, Any]:
        run = app.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.get("/approvals/pending", dependencies=[Depends(verify_token)])
    def pending_approvals() -> list[dict[str, Any]]:
        return app.state.store.list_pending_approvals()

    @app.post("/approvals/{request_id}/override", dependencies=[Depends(verify_token)])
    def override_approval(request_id: str, body: ApprovalOverrideBody) -> dict[str, Any]:
        ok = app.state.store.resolve_approval(request_id, body.status)
        if not ok:
            raise HTTPException(status_code=404, detail="approval not found")
        return {"request_id": request_id, "status": body.status}

    @app.get("/metrics", dependencies=[Depends(verify_token)])
    def metrics() -> dict[str, Any]:
        events_count = len(app.state.store.list_events()) if hasattr(app.state.store, "list_events") else 0
        runtime = _runtime_payload()["watchdog"]
        return {
            "active_sessions": len(app.state.store.list_sessions()),
            "pending_approvals": len(app.state.store.list_pending_approvals()),
            "recent_events": events_count,
            "active_helpers": int(runtime.get("active_helper_count", 0)),
            "oldest_helper_age_seconds": float(runtime.get("oldest_helper_age_seconds", 0.0)),
            "oldest_inflight_dispatch_seconds": float(runtime.get("oldest_inflight_dispatch_seconds", 0.0)),
            "busy": 1 if runtime.get("busy") else 0,
            "event_loop_lag_seconds": float(runtime.get("event_loop_lag_seconds", 0.0)),
        }

    @app.get("/audit/events", dependencies=[Depends(verify_token)])
    def audit_events(limit: int = 200) -> list[dict[str, Any]]:
        if not hasattr(app.state.store, "list_events"):
            return []
        return app.state.store.list_events(limit=limit)

    # --- Feature 4: Siri Shortcuts / Programmatic Task Submission ---

    @app.post("/task", dependencies=[Depends(verify_token)])
    def submit_task(body: TaskSubmission) -> dict[str, Any]:
        """Submit a task programmatically (for Shortcuts.app, curl, scripts).

        Requires an orchestrator to be injected via app.state.orchestrator.
        """
        if app.state.orchestrator is None:
            raise HTTPException(
                status_code=503,
                detail="Orchestrator not available. Start the daemon to enable task submission.",
            )

        # Validate sender against allowed list
        allowed = settings.allowed_senders
        if allowed and body.sender not in allowed:
            raise HTTPException(status_code=403, detail="Sender not in allowlist")

        msg = InboundMessage(
            id=f"api_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            sender=body.sender,
            text=body.text,
            received_at=datetime.now(UTC).isoformat(),
            is_from_me=False,
        )
        result = app.state.orchestrator.handle_message(msg)
        return {
            "kind": result.kind.value,
            "response": result.response,
            "run_id": result.run_id,
            "approval_request_id": result.approval_request_id,
        }

    return app


app = build_app()
