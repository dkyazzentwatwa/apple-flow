from __future__ import annotations

import secrets
import sqlite3
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from .config import RelaySettings
from .csv_audit import CsvAuditLogger
from .dashboard import (
    build_agent_office_item_detail,
    build_agent_office_summary,
    get_agent_office_section,
    resolve_agent_office_path,
)
from .gateway_health import read_all_gateway_health
from .models import InboundMessage
from .runtime_health import read_all_daemon_loop_health, read_daemon_watchdog
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.main")
_DASHBOARD_COOKIE_NAME = "apple_flow_dashboard_token"
_DASHBOARD_COOKIE_PATH = "/dashboard"


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


def _dashboard_auth_token(request: Request, token: str) -> str | None:
    if not token:
        return ""

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
        if secrets.compare_digest(provided, token):
            return provided

    cookie_token = request.cookies.get(_DASHBOARD_COOKIE_NAME, "")
    if cookie_token and secrets.compare_digest(cookie_token, token):
        return cookie_token

    return None


def _dashboard_now(settings: RelaySettings) -> datetime:
    tz_name = (settings.timezone or "").strip()
    if not tz_name:
        return datetime.now(UTC)
    try:
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        logger.warning("Invalid dashboard timezone %r; falling back to UTC", tz_name)
        return datetime.now(UTC)


def _dashboard_login_page() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Agent Office Dashboard Login</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f4f1ea;
        --panel: #ffffff;
        --text: #15202b;
        --muted: #5b6470;
        --line: #d8d1c4;
        --accent: #0f766e;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 20px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: radial-gradient(circle at top, #fffaf0 0, var(--bg) 55%, #e9ecef 100%);
        color: var(--text);
      }
      main {
        width: min(100%, 420px);
        padding: 24px;
        border: 1px solid var(--line);
        border-radius: 18px;
        background: var(--panel);
        box-shadow: 0 12px 30px rgba(21, 32, 43, 0.08);
      }
      h1 { margin: 0 0 8px; font-size: 1.8rem; }
      p { margin: 0 0 18px; color: var(--muted); }
      label { display: block; margin-bottom: 8px; font-weight: 600; }
      input {
        width: 100%;
        padding: 12px 14px;
        border: 1px solid var(--line);
        border-radius: 12px;
        font: inherit;
      }
      button {
        margin-top: 14px;
        width: 100%;
        padding: 12px 14px;
        border: 0;
        border-radius: 999px;
        background: var(--accent);
        color: white;
        font: inherit;
        cursor: pointer;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>Agent Office Dashboard</h1>
      <p>Enter your Apple Flow admin token to open the dashboard in this browser.</p>
      <form method="post" action="/dashboard/bootstrap">
        <label for="dashboard-token">Dashboard token</label>
        <input id="dashboard-token" name="dashboard_token" type="password" autocomplete="current-password" required>
        <button type="submit">Open dashboard</button>
      </form>
    </main>
  </body>
</html>"""


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

    app = FastAPI(title="Apple Flow Admin API", version="0.7.0")
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

    def _dashboard_summary() -> dict[str, Any]:
        office_path = resolve_agent_office_path(settings.soul_file)
        return build_agent_office_summary(
            office_path,
            store=app.state.store,
            config=settings,
            now=_dashboard_now(settings),
        )

    def _dashboard_html_path() -> Path:
        return Path(__file__).resolve().parent / "static" / "dashboard.html"

    async def verify_dashboard_auth(request: Request) -> None:
        if _dashboard_auth_token(request, settings.admin_api_token) is None:
            raise HTTPException(status_code=401, detail="Missing or invalid dashboard auth")

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

    @app.get("/dashboard/api/summary", dependencies=[Depends(verify_dashboard_auth)])
    def dashboard_summary() -> dict[str, Any]:
        return _dashboard_summary()

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard_page(request: Request) -> HTMLResponse:
        if not settings.admin_api_token:
            html_path = _dashboard_html_path()
            try:
                content = html_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise HTTPException(status_code=500, detail="dashboard shell not available") from exc
            return HTMLResponse(content=content)

        token = _dashboard_auth_token(request, settings.admin_api_token)
        if token is None:
            return HTMLResponse(content=_dashboard_login_page())
        html_path = _dashboard_html_path()
        try:
            content = html_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=500, detail="dashboard shell not available") from exc

        response = HTMLResponse(content=content)
        if request.cookies.get(_DASHBOARD_COOKIE_NAME) != token:
            response.set_cookie(
                key=_DASHBOARD_COOKIE_NAME,
                value=token,
                httponly=True,
                samesite="lax",
                secure=request.url.scheme == "https",
                path=_DASHBOARD_COOKIE_PATH,
            )
        return response

    @app.post("/dashboard/bootstrap")
    async def dashboard_bootstrap(request: Request) -> RedirectResponse:
        raw_body = (await request.body()).decode("utf-8", errors="replace")
        dashboard_token = parse_qs(raw_body).get("dashboard_token", [""])[0]
        if settings.admin_api_token and not secrets.compare_digest(dashboard_token, settings.admin_api_token):
            raise HTTPException(status_code=401, detail="Invalid dashboard token")

        response = RedirectResponse(url="/dashboard", status_code=303)
        if settings.admin_api_token:
            response.set_cookie(
                key=_DASHBOARD_COOKIE_NAME,
                value=dashboard_token,
                httponly=True,
                samesite="lax",
                secure=request.url.scheme == "https",
                path=_DASHBOARD_COOKIE_PATH,
            )
        return response

    @app.get("/dashboard/api/section/{section_name}", dependencies=[Depends(verify_dashboard_auth)])
    def dashboard_section(section_name: str) -> dict[str, Any]:
        summary = _dashboard_summary()
        try:
            return get_agent_office_section(summary, section_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="dashboard section not found") from exc

    @app.get("/dashboard/api/item", dependencies=[Depends(verify_dashboard_auth)])
    def dashboard_item(section: str, name: str = "", bucket: str = "") -> dict[str, Any]:
        office_path = resolve_agent_office_path(settings.soul_file)
        try:
            return build_agent_office_item_detail(
                office_path,
                section=section,
                name=name,
                bucket=bucket,
                now=_dashboard_now(settings),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="dashboard item not found") from exc

    @app.post("/dashboard/api/companion/mute", dependencies=[Depends(verify_dashboard_auth)])
    def dashboard_companion_mute() -> dict[str, Any]:
        if hasattr(app.state.store, "set_state"):
            app.state.store.set_state("companion_muted", "true")
        else:
            raise HTTPException(status_code=500, detail="store does not support state updates")
        return {"companion_muted": True}

    @app.post("/dashboard/api/companion/unmute", dependencies=[Depends(verify_dashboard_auth)])
    def dashboard_companion_unmute() -> dict[str, Any]:
        if hasattr(app.state.store, "set_state"):
            app.state.store.set_state("companion_muted", "false")
        else:
            raise HTTPException(status_code=500, detail="store does not support state updates")
        return {"companion_muted": False}

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
