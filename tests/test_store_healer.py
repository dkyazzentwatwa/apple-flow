"""Tests for SQLiteStore healer subsystem and other untested store methods."""

from __future__ import annotations

from apple_flow.store import SQLiteStore


def _make_store(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    return store


def _create_issue(store, issue_id="issue_1", repo="org/repo", title="Bug", body="desc", author="user1", labels=None):
    store.upsert_healer_issue(
        issue_id=issue_id,
        repo=repo,
        title=title,
        body=body,
        author=author,
        labels=labels or ["bug"],
        priority=50,
    )


# ---------------------------------------------------------------------------
# record_message
# ---------------------------------------------------------------------------

def test_record_message_new_returns_true(tmp_path):
    store = _make_store(tmp_path)
    result = store.record_message(
        message_id="msg_1",
        sender="+15551234567",
        text="hello",
        received_at="2026-01-01T12:00:00Z",
        dedupe_hash="hash1",
    )
    assert result is True


def test_record_message_duplicate_returns_false(tmp_path):
    store = _make_store(tmp_path)
    store.record_message("msg_1", "+1", "hello", "2026-01-01T12:00:00Z", "hash1")
    result = store.record_message("msg_1", "+1", "hello", "2026-01-01T12:00:00Z", "hash1")
    assert result is False


# ---------------------------------------------------------------------------
# list_active_runs, get_run_source_context
# ---------------------------------------------------------------------------

def test_list_active_runs(tmp_path):
    store = _make_store(tmp_path)
    store.create_run("run_a", "+1", "task", "executing", "/tmp", "execute")
    store.create_run("run_b", "+1", "task", "completed", "/tmp", "execute")

    active = store.list_active_runs()
    active_ids = [r["run_id"] for r in active]
    assert "run_a" in active_ids
    assert "run_b" not in active_ids


def test_get_run_source_context(tmp_path):
    store = _make_store(tmp_path)
    store.create_run(
        "run_1", "+1", "task", "executing", "/tmp", "execute",
        source_context={"channel": "notes", "note_id": "n1"}
    )
    ctx = store.get_run_source_context("run_1")
    assert ctx is not None
    assert ctx.get("channel") == "notes"
    assert ctx.get("note_id") == "n1"


def test_get_run_source_context_missing(tmp_path):
    store = _make_store(tmp_path)
    ctx = store.get_run_source_context("nonexistent")
    assert ctx is None


# ---------------------------------------------------------------------------
# get_approval, deny_all_approvals, resolve_approval
# ---------------------------------------------------------------------------

def test_get_approval_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    store.create_run("run_1", "+1", "task", "awaiting_approval", "/tmp", "execute")
    store.create_approval(
        request_id="req_1",
        run_id="run_1",
        summary="Do thing",
        command_preview="mkdir",
        expires_at="2099-01-01T00:00:00Z",
        sender="+1",
    )
    approval = store.get_approval("req_1")
    assert approval is not None
    assert approval["request_id"] == "req_1"
    assert approval["status"] == "pending"


def test_get_approval_missing(tmp_path):
    store = _make_store(tmp_path)
    assert store.get_approval("nonexistent") is None


def test_deny_all_approvals(tmp_path):
    store = _make_store(tmp_path)
    for i in range(3):
        store.create_run(f"run_{i}", "+1", "task", "awaiting_approval", "/tmp", "execute")
        store.create_approval(
            request_id=f"req_{i}",
            run_id=f"run_{i}",
            summary="Do thing",
            command_preview="cmd",
            expires_at="2099-01-01T00:00:00Z",
            sender="+1",
        )
    count = store.deny_all_approvals()
    assert count == 3
    assert len(store.list_pending_approvals()) == 0


def test_deny_all_approvals_none_pending(tmp_path):
    store = _make_store(tmp_path)
    count = store.deny_all_approvals()
    assert count == 0


def test_resolve_approval(tmp_path):
    store = _make_store(tmp_path)
    store.create_run("run_1", "+1", "task", "awaiting_approval", "/tmp", "execute")
    store.create_approval("req_1", "run_1", "s", "p", "2099-01-01T00:00:00Z", "+1")
    ok = store.resolve_approval("req_1", "approved")
    assert ok is True
    approval = store.get_approval("req_1")
    assert approval["status"] == "approved"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def test_create_and_list_events_for_run(tmp_path):
    store = _make_store(tmp_path)
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    store.create_event("evt_1", "run_1", "executor", "started", {"attempt": 1})
    store.create_event("evt_2", "run_1", "executor", "completed", {"snippet": "done"})

    events = store.list_events_for_run("run_1", limit=10)
    assert len(events) == 2
    event_types = [e["event_type"] for e in events]
    assert "started" in event_types
    assert "completed" in event_types


def test_list_events(tmp_path):
    store = _make_store(tmp_path)
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    store.create_event("evt_1", "run_1", "executor", "started", {})
    events = store.list_events(limit=10)
    assert len(events) >= 1


def test_get_latest_event_for_run(tmp_path):
    store = _make_store(tmp_path)
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    store.create_event("evt_1", "run_1", "executor", "started", {"attempt": 1})
    store.create_event("evt_2", "run_1", "executor", "heartbeat", {"msg": "working"})

    latest = store.get_latest_event_for_run("run_1")
    assert latest is not None
    assert latest["run_id"] == "run_1"
    assert latest["event_type"] in {"started", "heartbeat"}


def test_get_latest_event_for_run_no_events(tmp_path):
    store = _make_store(tmp_path)
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    latest = store.get_latest_event_for_run("run_1")
    assert latest is None


def test_count_run_events(tmp_path):
    store = _make_store(tmp_path)
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    store.create_event("evt_1", "run_1", "executor", "execution_started", {})
    store.create_event("evt_2", "run_1", "executor", "execution_started", {})
    store.create_event("evt_3", "run_1", "executor", "completed", {})

    count = store.count_run_events("run_1", event_type="execution_started")
    assert count == 2


# ---------------------------------------------------------------------------
# cancel_run_jobs
# ---------------------------------------------------------------------------

def test_cancel_run_jobs(tmp_path):
    store = _make_store(tmp_path)
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    store.enqueue_run_job(job_id="job_1", run_id="run_1", sender="+1", phase="executor", attempt=1, payload={})
    store.enqueue_run_job(job_id="job_2", run_id="run_1", sender="+1", phase="executor", attempt=2, payload={})

    cancelled = store.cancel_run_jobs("run_1")
    assert cancelled >= 1
    jobs = store.list_run_jobs(run_id="run_1")
    statuses = {j["status"] for j in jobs}
    assert "cancelled" in statuses


# ---------------------------------------------------------------------------
# Healer: upsert_healer_issue, get_healer_issue, list_healer_issues
# ---------------------------------------------------------------------------

def test_upsert_healer_issue_creates(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    issue = store.get_healer_issue("issue_1")
    assert issue is not None
    assert issue["issue_id"] == "issue_1"
    assert issue["repo"] == "org/repo"
    assert issue["state"] == "queued"
    assert issue["labels"] == ["bug"]


def test_upsert_healer_issue_updates(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store, title="Original")
    _create_issue(store, title="Updated")
    issue = store.get_healer_issue("issue_1")
    assert issue["title"] == "Updated"


def test_get_healer_issue_missing(tmp_path):
    store = _make_store(tmp_path)
    assert store.get_healer_issue("nonexistent") is None


def test_list_healer_issues_all(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store, issue_id="issue_1")
    _create_issue(store, issue_id="issue_2")
    issues = store.list_healer_issues()
    assert len(issues) == 2


def test_list_healer_issues_by_state(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store, issue_id="issue_1")
    issues = store.list_healer_issues(states=["queued"])
    assert len(issues) == 1
    assert issues[0]["state"] == "queued"

    issues_claimed = store.list_healer_issues(states=["claimed"])
    assert len(issues_claimed) == 0


# ---------------------------------------------------------------------------
# Healer: claim_next_healer_issue, renew_healer_issue_lease
# ---------------------------------------------------------------------------

def test_claim_next_healer_issue(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    claimed = store.claim_next_healer_issue(worker_id="worker_1", lease_seconds=60)
    assert claimed is not None
    assert claimed["state"] == "claimed"
    assert claimed["lease_owner"] == "worker_1"


def test_claim_next_healer_issue_empty(tmp_path):
    store = _make_store(tmp_path)
    claimed = store.claim_next_healer_issue(worker_id="worker_1", lease_seconds=60)
    assert claimed is None


def test_renew_healer_issue_lease(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    store.claim_next_healer_issue(worker_id="worker_1", lease_seconds=60)
    ok = store.renew_healer_issue_lease(issue_id="issue_1", worker_id="worker_1", lease_seconds=120)
    assert ok is True


def test_renew_healer_issue_lease_wrong_worker(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    store.claim_next_healer_issue(worker_id="worker_1", lease_seconds=60)
    ok = store.renew_healer_issue_lease(issue_id="issue_1", worker_id="wrong_worker", lease_seconds=120)
    assert ok is False


# ---------------------------------------------------------------------------
# Healer: increment_healer_attempt, set_healer_issue_state
# ---------------------------------------------------------------------------

def test_increment_healer_attempt(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    count1 = store.increment_healer_attempt("issue_1")
    count2 = store.increment_healer_attempt("issue_1")
    assert count1 == 1
    assert count2 == 2


def test_set_healer_issue_state(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    ok = store.set_healer_issue_state(issue_id="issue_1", state="running")
    assert ok is True
    issue = store.get_healer_issue("issue_1")
    assert issue["state"] == "running"


def test_set_healer_issue_state_with_branch(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    ok = store.set_healer_issue_state(
        issue_id="issue_1",
        state="running",
        branch_name="fix/issue-1",
        workspace_path="/workspace/repo",
    )
    assert ok is True
    issue = store.get_healer_issue("issue_1")
    assert issue["branch_name"] == "fix/issue-1"
    assert issue["workspace_path"] == "/workspace/repo"


def test_set_healer_issue_state_clear_lease(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    store.claim_next_healer_issue(worker_id="worker_1", lease_seconds=60)
    store.set_healer_issue_state(issue_id="issue_1", state="queued", clear_lease=True)
    issue = store.get_healer_issue("issue_1")
    assert issue.get("lease_owner") is None


# ---------------------------------------------------------------------------
# Healer: requeue_expired_healer_issue_leases
# ---------------------------------------------------------------------------

def test_requeue_expired_healer_issue_leases(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    store.claim_next_healer_issue(worker_id="worker_1", lease_seconds=60)

    # Force lease expiry
    conn = store._connect()
    with store._lock:
        conn.execute(
            "UPDATE healer_issues SET lease_expires_at='2000-01-01T00:00:00' WHERE issue_id='issue_1'"
        )
        conn.commit()

    count = store.requeue_expired_healer_issue_leases()
    assert count == 1
    issue = store.get_healer_issue("issue_1")
    assert issue["state"] == "queued"


# ---------------------------------------------------------------------------
# Healer: create_healer_attempt, finish_healer_attempt, list_healer_attempts
# ---------------------------------------------------------------------------

def test_create_and_list_healer_attempts(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    store.create_healer_attempt(
        attempt_id="attempt_1",
        issue_id="issue_1",
        attempt_no=1,
        state="running",
        prediction_source="gpt",
        predicted_lock_set=["file_a.py"],
    )
    attempts = store.list_healer_attempts(issue_id="issue_1")
    assert len(attempts) == 1
    assert attempts[0]["attempt_id"] == "attempt_1"
    assert attempts[0]["predicted_lock_set"] == ["file_a.py"]


def test_finish_healer_attempt(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    store.create_healer_attempt(
        attempt_id="attempt_1",
        issue_id="issue_1",
        attempt_no=1,
        state="running",
        prediction_source="gpt",
        predicted_lock_set=[],
    )
    ok = store.finish_healer_attempt(
        attempt_id="attempt_1",
        state="completed",
        actual_diff_set=["file_a.py"],
        test_summary={"passed": 5, "failed": 0},
        verifier_summary={"verified": True},
    )
    assert ok is True
    attempts = store.list_healer_attempts(issue_id="issue_1")
    assert attempts[0]["state"] == "completed"
    assert attempts[0]["actual_diff_set"] == ["file_a.py"]


def test_list_recent_healer_attempts(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store, issue_id="i1")
    _create_issue(store, issue_id="i2")
    store.create_healer_attempt(attempt_id="a1", issue_id="i1", attempt_no=1, state="running", prediction_source="gpt", predicted_lock_set=[])
    store.create_healer_attempt(attempt_id="a2", issue_id="i2", attempt_no=1, state="running", prediction_source="gpt", predicted_lock_set=[])
    attempts = store.list_recent_healer_attempts(limit=10)
    assert len(attempts) == 2


def test_healer_attempt_with_failure(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    store.create_healer_attempt(attempt_id="a1", issue_id="issue_1", attempt_no=1, state="running", prediction_source="gpt", predicted_lock_set=[])
    store.finish_healer_attempt(
        attempt_id="a1",
        state="failed",
        actual_diff_set=[],
        test_summary={},
        verifier_summary={},
        failure_class="TestFailure",
        failure_reason="assertion error in test_foo.py",
    )
    attempts = store.list_healer_attempts(issue_id="issue_1")
    assert attempts[0]["failure_class"] == "TestFailure"
    assert "assertion error" in attempts[0]["failure_reason"]


# ---------------------------------------------------------------------------
# Healer: create_healer_lesson, list_healer_lessons, mark_healer_lessons_used
# ---------------------------------------------------------------------------

def test_create_and_list_healer_lessons(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    store.create_healer_attempt(attempt_id="a1", issue_id="issue_1", attempt_no=1, state="running", prediction_source="gpt", predicted_lock_set=[])
    store.create_healer_lesson(
        lesson_id="lesson_1",
        issue_id="issue_1",
        attempt_id="a1",
        lesson_kind="root_cause",
        scope_key="org/repo",
        fingerprint="fp_abc",
        problem_summary="null pointer in auth",
        lesson_text="Always check for null before calling .get()",
        test_hint="test_auth.py",
        guardrail={"max_diff_files": 3},
        confidence=80,
        outcome="success",
    )
    lessons = store.list_healer_lessons(limit=10)
    assert len(lessons) == 1
    assert lessons[0]["lesson_id"] == "lesson_1"
    assert lessons[0]["guardrail"]["max_diff_files"] == 3


def test_mark_healer_lessons_used(tmp_path):
    store = _make_store(tmp_path)
    _create_issue(store)
    store.create_healer_attempt(attempt_id="a1", issue_id="issue_1", attempt_no=1, state="running", prediction_source="gpt", predicted_lock_set=[])
    store.create_healer_lesson(
        lesson_id="lesson_1",
        issue_id="issue_1",
        attempt_id="a1",
        lesson_kind="root_cause",
        scope_key="org/repo",
        fingerprint="fp_abc",
        problem_summary="null ptr",
        lesson_text="check nulls",
        test_hint="test.py",
        guardrail={},
        confidence=70,
        outcome="success",
    )
    count = store.mark_healer_lessons_used(["lesson_1"])
    assert count == 1


# ---------------------------------------------------------------------------
# get_stats, recent_messages, search_messages
# ---------------------------------------------------------------------------

def test_get_stats_empty(tmp_path):
    store = _make_store(tmp_path)
    stats = store.get_stats()
    assert "active_sessions" in stats or isinstance(stats, dict)


def test_recent_messages(tmp_path):
    store = _make_store(tmp_path)
    store.record_message("m1", "+1", "hello", "2026-01-01T12:00:00Z", "h1")
    store.record_message("m2", "+1", "world", "2026-01-01T12:01:00Z", "h2")
    messages = store.recent_messages("+1", limit=10)
    assert len(messages) >= 1


def test_search_messages(tmp_path):
    store = _make_store(tmp_path)
    store.record_message("m1", "+1", "hello world", "2026-01-01T12:00:00Z", "h1")
    results = store.search_messages("+1", "hello", limit=10)
    assert len(results) >= 1
    assert any("hello" in r.get("text", "") for r in results)


def test_search_messages_no_results(tmp_path):
    store = _make_store(tmp_path)
    results = store.search_messages("+1", "xyz_no_match", limit=10)
    assert results == []


# ---------------------------------------------------------------------------
# close() method
# ---------------------------------------------------------------------------

def test_store_close(tmp_path):
    store = _make_store(tmp_path)
    # Should not raise
    store.close()


def test_store_close_idempotent(tmp_path):
    store = _make_store(tmp_path)
    store.close()
    store.close()  # Second close should not raise
