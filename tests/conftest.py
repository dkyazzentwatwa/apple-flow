"""Shared test fixtures for Apple Flow tests."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@dataclass
class FakeConnector:
    """Fake connector for testing orchestrator logic."""

    created: list[str] = field(default_factory=list)
    turns: list[tuple[str, str]] = field(default_factory=list)

    def get_or_create_thread(self, sender: str) -> str:
        self.created.append(sender)
        return "thread_abc"

    def reset_thread(self, sender: str) -> str:
        self.created.append(f"reset:{sender}")
        return "thread_reset"

    def run_turn(self, thread_id: str, prompt: str) -> str:
        self.turns.append((thread_id, prompt))
        if "planner" in prompt:
            return "PLAN: Create files and tests"
        if "verifier" in prompt:
            return "VERIFIED: checks complete"
        return "assistant-response"

    def ensure_started(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


class FakeEgress:
    """Fake egress for testing message sending."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, recipient: str, text: str, context: dict[str, Any] | None = None) -> None:
        self.messages.append((recipient, text))

    def was_recent_outbound(self, sender: str, text: str) -> bool:
        return False

    def mark_outbound(self, recipient: str, text: str) -> None:
        pass


class FakeStore:
    """Fake store for testing orchestrator logic."""

    def __init__(self) -> None:
        self.approvals: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.state: dict[str, str] = {}
        self.run_jobs: dict[str, dict[str, Any]] = {}
        self.healer_issues: dict[str, dict[str, Any]] = {}
        self.healer_attempts: list[dict[str, Any]] = []
        self.healer_lessons: list[dict[str, Any]] = []
        self.healer_locks: list[dict[str, Any]] = []
        self.scan_runs: dict[str, dict[str, Any]] = {}
        self.scan_findings: dict[str, dict[str, Any]] = {}

    def bootstrap(self) -> None:
        pass

    def close(self) -> None:
        pass

    def record_message(
        self, message_id: str, sender: str, text: str, received_at: str, dedupe_hash: str
    ) -> bool:
        if message_id in self.messages:
            return False
        self.messages[message_id] = {
            "sender": sender,
            "text": text,
            "received_at": received_at,
            "dedupe_hash": dedupe_hash,
        }
        return True

    def get_session(self, sender: str) -> dict[str, Any] | None:
        return self.sessions.get(sender)

    def upsert_session(self, sender: str, thread_id: str, mode: str) -> None:
        self.sessions[sender] = {"thread_id": thread_id, "mode": mode}

    def list_sessions(self) -> list[dict[str, Any]]:
        return list(self.sessions.values())

    def create_run(
        self,
        run_id: str,
        sender: str,
        intent: str,
        state: str,
        cwd: str,
        risk_level: str,
        source_context: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.runs[run_id] = {
            "run_id": run_id,
            "state": state,
            "sender": sender,
            "intent": intent,
            "cwd": cwd,
            "risk_level": risk_level,
            "source_context": source_context,
            "created_at": now,
            "updated_at": now,
        }

    def update_run_state(self, run_id: str, state: str) -> None:
        if run_id in self.runs:
            self.runs[run_id]["state"] = state
            self.runs[run_id]["updated_at"] = datetime.now(UTC).isoformat()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.runs.get(run_id)

    def list_active_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        active = [
            run for run in self.runs.values()
            if run.get("state") in {"planning", "awaiting_approval", "queued", "running", "executing", "verifying"}
        ]
        return active[:limit]

    def get_run_source_context(self, run_id: str) -> dict[str, Any] | None:
        """Get the source context for a run (reminder_id, note_id, etc.)"""
        run = self.get_run(run_id)
        if not run:
            return None
        return run.get("source_context")

    def create_approval(
        self,
        request_id: str,
        run_id: str,
        summary: str,
        command_preview: str,
        expires_at: str,
        sender: str,
    ) -> None:
        self.approvals[request_id] = {
            "request_id": request_id,
            "run_id": run_id,
            "sender": sender,
            "summary": summary,
            "command_preview": command_preview,
            "expires_at": expires_at,
            "status": "pending",
        }

    def get_approval(self, request_id: str) -> dict[str, Any] | None:
        return self.approvals.get(request_id)

    def resolve_approval(self, request_id: str, status: str) -> bool:
        if request_id in self.approvals:
            self.approvals[request_id]["status"] = status
            return True
        return False

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return [a for a in self.approvals.values() if a.get("status") == "pending"]

    def create_event(
        self, event_id: str, run_id: str, step: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        self.events.append(
            {
                "event_id": event_id,
                "run_id": run_id,
                "step": step,
                "event_type": event_type,
                "payload": payload,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

    def list_events(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.events[:limit]

    def list_events_for_run(self, run_id: str, limit: int = 50) -> list[dict[str, Any]]:
        events = [event for event in self.events if event.get("run_id") == run_id]
        return list(reversed(events))[:limit]

    def get_latest_event_for_run(self, run_id: str) -> dict[str, Any] | None:
        events = self.list_events_for_run(run_id, limit=1)
        if not events:
            return None
        return events[0]

    def count_run_events(self, run_id: str, event_type: str | None = None) -> int:
        events = self.list_events_for_run(run_id, limit=500)
        if event_type:
            events = [event for event in events if event.get("event_type") == event_type]
        return len(events)

    def set_state(self, key: str, value: str) -> None:
        self.state[key] = value

    def get_state(self, key: str) -> str | None:
        return self.state.get(key)

    def enqueue_run_job(
        self,
        *,
        job_id: str,
        run_id: str,
        sender: str,
        phase: str,
        attempt: int,
        payload: dict[str, Any] | None = None,
        status: str = "queued",
    ) -> None:
        self.run_jobs[job_id] = {
            "job_id": job_id,
            "run_id": run_id,
            "sender": sender,
            "phase": phase,
            "attempt": attempt,
            "payload": payload or {},
            "status": status,
        }

    def cancel_run_jobs(self, run_id: str) -> int:
        count = 0
        for job in self.run_jobs.values():
            if job.get("run_id") != run_id:
                continue
            if job.get("status") not in {"queued", "running"}:
                continue
            job["status"] = "cancelled"
            count += 1
        return count

    def get_stats(self) -> dict[str, Any]:
        runs_by_state: dict[str, int] = {}
        for run in self.runs.values():
            state = run.get("state", "unknown")
            runs_by_state[state] = runs_by_state.get(state, 0) + 1
        return {
            "active_sessions": len(self.sessions),
            "total_messages": len(self.messages),
            "pending_approvals": len(self.list_pending_approvals()),
            "runs_by_state": runs_by_state,
            "last_event": self.events[-1] if self.events else None,
        }

    # --- Healer helpers (for system: healer tests) ---

    def upsert_healer_issue(
        self,
        *,
        issue_id: str,
        repo: str,
        title: str,
        body: str,
        author: str,
        labels: list[str],
        priority: int = 100,
    ) -> None:
        self.healer_issues[issue_id] = {
            "issue_id": issue_id,
            "repo": repo,
            "title": title,
            "body": body,
            "author": author,
            "labels": list(labels),
            "priority": int(priority),
            "state": self.healer_issues.get(issue_id, {}).get("state", "queued"),
        }

    def set_healer_issue_state(
        self,
        *,
        issue_id: str,
        state: str,
        **_kwargs: Any,
    ) -> bool:
        issue = self.healer_issues.get(issue_id)
        if issue is None:
            return False
        issue["state"] = state
        return True

    def list_healer_issues(self, *, states: list[str] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        issues = list(self.healer_issues.values())
        if states:
            state_set = set(states)
            issues = [item for item in issues if item.get("state") in state_set]
        return issues[:limit]

    def create_healer_attempt(
        self,
        *,
        attempt_id: str,
        issue_id: str,
        attempt_no: int,
        state: str,
        prediction_source: str,
        predicted_lock_set: list[str],
    ) -> None:
        self.healer_attempts.append(
            {
                "attempt_id": attempt_id,
                "issue_id": issue_id,
                "attempt_no": attempt_no,
                "state": state,
                "prediction_source": prediction_source,
                "predicted_lock_set": list(predicted_lock_set),
            }
        )

    def finish_healer_attempt(
        self,
        *,
        attempt_id: str,
        state: str,
        actual_diff_set: list[str],
        test_summary: dict[str, Any],
        verifier_summary: dict[str, Any],
        failure_class: str = "",
        failure_reason: str = "",
    ) -> bool:
        for attempt in self.healer_attempts:
            if attempt.get("attempt_id") == attempt_id:
                attempt["state"] = state
                attempt["actual_diff_set"] = list(actual_diff_set)
                attempt["test_summary"] = dict(test_summary)
                attempt["verifier_summary"] = dict(verifier_summary)
                attempt["failure_class"] = failure_class
                attempt["failure_reason"] = failure_reason
                return True
        return False

    def list_recent_healer_attempts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self.healer_attempts))[:limit]

    def create_healer_lesson(
        self,
        *,
        lesson_id: str,
        issue_id: str,
        attempt_id: str,
        lesson_kind: str,
        scope_key: str,
        fingerprint: str,
        problem_summary: str,
        lesson_text: str,
        test_hint: str,
        guardrail: dict[str, Any],
        confidence: int,
        outcome: str,
    ) -> None:
        self.healer_lessons.append(
            {
                "lesson_id": lesson_id,
                "issue_id": issue_id,
                "attempt_id": attempt_id,
                "lesson_kind": lesson_kind,
                "scope_key": scope_key,
                "fingerprint": fingerprint,
                "problem_summary": problem_summary,
                "lesson_text": lesson_text,
                "test_hint": test_hint,
                "guardrail": dict(guardrail or {}),
                "confidence": confidence,
                "outcome": outcome,
                "use_count": 0,
                "last_used_at": None,
            }
        )

    def list_healer_lessons(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return list(reversed(self.healer_lessons))[:limit]

    def mark_healer_lessons_used(self, lesson_ids: list[str]) -> int:
        updated = 0
        wanted = set(lesson_ids)
        for lesson in self.healer_lessons:
            if lesson.get("lesson_id") not in wanted:
                continue
            lesson["use_count"] = int(lesson.get("use_count", 0)) + 1
            lesson["last_used_at"] = datetime.now(UTC).isoformat()
            updated += 1
        return updated

    def get_healer_lesson_stats(self) -> dict[str, Any]:
        recurring: dict[str, int] = {}
        recently_used = 0
        for lesson in self.healer_lessons:
            guardrail = lesson.get("guardrail", {})
            failure_class = str(guardrail.get("failure_class") or "")
            if failure_class:
                recurring[failure_class] = recurring.get(failure_class, 0) + 1
            if lesson.get("last_used_at"):
                recently_used += 1
        return {
            "total_lessons": len(self.healer_lessons),
            "recently_used": recently_used,
            "top_failure_classes": [
                {"failure_class": key, "count": count}
                for key, count in sorted(recurring.items(), key=lambda item: (-item[1], item[0]))[:3]
            ],
        }

    def list_healer_locks(self, *, issue_id: str | None = None) -> list[dict[str, Any]]:
        if issue_id is None:
            return list(self.healer_locks)
        return [entry for entry in self.healer_locks if entry.get("issue_id") == issue_id]

    # --- Scan pipeline helpers ---

    def create_scan_run(self, *, run_id: str, dry_run: bool) -> None:
        now = datetime.now(UTC).isoformat()
        self.scan_runs[run_id] = {
            "run_id": run_id,
            "status": "running",
            "dry_run": bool(dry_run),
            "summary": {},
            "created_at": now,
            "updated_at": now,
        }

    def finish_scan_run(self, *, run_id: str, status: str, summary: dict[str, Any]) -> bool:
        run = self.scan_runs.get(run_id)
        if run is None:
            return False
        run["status"] = status
        run["summary"] = dict(summary or {})
        run["updated_at"] = datetime.now(UTC).isoformat()
        return True

    def get_scan_finding(self, fingerprint: str) -> dict[str, Any] | None:
        finding = self.scan_findings.get(fingerprint)
        if finding is None:
            return None
        return dict(finding)

    def upsert_scan_finding(
        self,
        *,
        fingerprint: str,
        scan_type: str,
        severity: str,
        title: str,
        status: str,
        payload: dict[str, Any],
        issue_number: int | None = None,
    ) -> None:
        existing = self.scan_findings.get(fingerprint, {})
        now = datetime.now(UTC).isoformat()
        self.scan_findings[fingerprint] = {
            "fingerprint": fingerprint,
            "scan_type": scan_type,
            "severity": severity,
            "title": title,
            "status": status,
            "payload": dict(payload or {}),
            "issue_number": issue_number if issue_number is not None else existing.get("issue_number"),
            "first_seen_at": existing.get("first_seen_at", now),
            "last_seen_at": now,
        }

    def list_scan_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = sorted(
            self.scan_runs.values(),
            key=lambda row: str(row.get("created_at", "")),
            reverse=True,
        )
        return [dict(row) for row in rows[:limit]]

    def list_scan_findings(self, *, limit: int = 200) -> list[dict[str, Any]]:
        rows = sorted(
            self.scan_findings.values(),
            key=lambda row: str(row.get("last_seen_at", "")),
            reverse=True,
        )
        return [dict(row) for row in rows[:limit]]

    def recent_messages(self, sender: str, limit: int = 10) -> list[dict[str, Any]]:
        sender_msgs = [
            m for mid, m in self.messages.items() if m.get("sender") == sender
        ]
        return sender_msgs[:limit]

    def search_messages(self, sender: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
        results = [
            m for mid, m in self.messages.items()
            if m.get("sender") == sender and query.lower() in (m.get("text", "")).lower()
        ]
        return results[:limit]


@pytest.fixture
def fake_connector() -> FakeConnector:
    """Provide a fake connector for tests."""
    return FakeConnector()


@pytest.fixture
def fake_egress() -> FakeEgress:
    """Provide a fake egress for tests."""
    return FakeEgress()


@pytest.fixture
def fake_store() -> FakeStore:
    """Provide a fake store for tests."""
    return FakeStore()
