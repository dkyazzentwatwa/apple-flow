from __future__ import annotations

import json
from typing import Any


KNOWN_DAEMON_LOOPS = (
    "imessage",
    "run_executor",
    "mail",
    "reminders",
    "notes",
    "calendar",
    "companion",
    "ambient",
    "memory_maintenance",
    "helper_maintenance",
    "event_loop_watchdog",
)


def daemon_loop_health_state_key(name: str) -> str:
    return f"daemon_loop_health_{name}"


def daemon_watchdog_state_key() -> str:
    return "daemon_watchdog"


def daemon_loop_health_payload(
    *,
    healthy: bool,
    last_success_at: str = "",
    last_failure_at: str = "",
    last_failure_reason: str = "",
    restart_count: int = 0,
    last_restart_at: str = "",
) -> str:
    return json.dumps(
        {
            "healthy": healthy,
            "last_success_at": last_success_at,
            "last_failure_at": last_failure_at,
            "last_failure_reason": last_failure_reason,
            "restart_count": int(restart_count),
            "last_restart_at": last_restart_at,
        }
    )


def daemon_watchdog_payload(
    *,
    healthy: bool,
    degraded_reasons: list[str] | None = None,
    last_connector_completion_at: str = "",
    oldest_inflight_dispatch_seconds: float = 0.0,
    active_helper_count: int = 0,
    oldest_helper_age_seconds: float = 0.0,
    event_loop_lag_seconds: float = 0.0,
    event_loop_lag_failures: int = 0,
) -> str:
    return json.dumps(
        {
            "healthy": healthy,
            "degraded_reasons": list(degraded_reasons or []),
            "last_connector_completion_at": last_connector_completion_at,
            "oldest_inflight_dispatch_seconds": float(oldest_inflight_dispatch_seconds),
            "active_helper_count": int(active_helper_count),
            "oldest_helper_age_seconds": float(oldest_helper_age_seconds),
            "event_loop_lag_seconds": float(event_loop_lag_seconds),
            "event_loop_lag_failures": int(event_loop_lag_failures),
        }
    )


def _read_json_state(store: Any, key: str) -> dict[str, Any] | None:
    if not hasattr(store, "get_state"):
        return None
    raw = store.get_state(key)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def read_daemon_loop_health(store: Any, name: str) -> dict[str, Any] | None:
    return _read_json_state(store, daemon_loop_health_state_key(name))


def read_all_daemon_loop_health(store: Any) -> dict[str, dict[str, Any]]:
    return {
        name: state
        for name in KNOWN_DAEMON_LOOPS
        if (state := read_daemon_loop_health(store, name)) is not None
    }


def read_daemon_watchdog(store: Any) -> dict[str, Any] | None:
    return _read_json_state(store, daemon_watchdog_state_key())


def summarize_runtime_health_lines(store: Any) -> list[str]:
    lines: list[str] = []
    watchdog = read_daemon_watchdog(store)
    if watchdog:
        status = "OK" if watchdog.get("healthy", True) else "DEGRADED"
        line = f"Runtime: {status}"
        reasons = [str(reason) for reason in watchdog.get("degraded_reasons", []) if str(reason)]
        if reasons:
            line += " | " + ", ".join(reasons)
        if "oldest_inflight_dispatch_seconds" in watchdog:
            line += f" | inflight {int(float(watchdog.get('oldest_inflight_dispatch_seconds', 0.0)))}s"
        if "active_helper_count" in watchdog:
            line += f" | helpers {int(watchdog.get('active_helper_count', 0))}"
        if "event_loop_lag_seconds" in watchdog:
            line += f" | loop lag {float(watchdog.get('event_loop_lag_seconds', 0.0)):.2f}s"
        lines.append(line)

    for name, state in read_all_daemon_loop_health(store).items():
        status = "OK" if state.get("healthy", True) else "DEGRADED"
        line = f"Loop {name}: {status}"
        if state.get("restart_count"):
            line += f" | restarts {int(state['restart_count'])}"
        if state.get("last_failure_reason") and not state.get("healthy", True):
            line += f" | {state['last_failure_reason']}"
        lines.append(line)
    return lines
