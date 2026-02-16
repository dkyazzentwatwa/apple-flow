from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import RelaySettings
from .store import SQLiteStore


class ApprovalOverrideBody(BaseModel):
    status: str = Field(pattern="^(approved|denied)$")


def build_app(store: Any | None = None) -> FastAPI:
    settings = RelaySettings()
    active_store = store if store is not None else SQLiteStore(Path(settings.db_path))
    if hasattr(active_store, "bootstrap"):
        active_store.bootstrap()

    app = FastAPI(title="Codex Relay Admin API", version="0.1.0")
    app.state.store = active_store

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/sessions")
    def sessions() -> list[dict[str, Any]]:
        return app.state.store.list_sessions()

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = app.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.get("/approvals/pending")
    def pending_approvals() -> list[dict[str, Any]]:
        return app.state.store.list_pending_approvals()

    @app.post("/approvals/{request_id}/override")
    def override_approval(request_id: str, body: ApprovalOverrideBody) -> dict[str, Any]:
        ok = app.state.store.resolve_approval(request_id, body.status)
        if not ok:
            raise HTTPException(status_code=404, detail="approval not found")
        return {"request_id": request_id, "status": body.status}

    @app.get("/metrics")
    def metrics() -> dict[str, int]:
        events_count = len(app.state.store.list_events()) if hasattr(app.state.store, "list_events") else 0
        return {
            "active_sessions": len(app.state.store.list_sessions()),
            "pending_approvals": len(app.state.store.list_pending_approvals()),
            "recent_events": events_count,
        }

    @app.get("/audit/events")
    def audit_events(limit: int = 200) -> list[dict[str, Any]]:
        if not hasattr(app.state.store, "list_events"):
            return []
        return app.state.store.list_events(limit=limit)

    return app


app = build_app()
