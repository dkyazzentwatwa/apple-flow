from apple_flow.store import SQLiteStore


def test_store_bootstrap_and_session_roundtrip(tmp_path):
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.upsert_session(sender="+15551234567", thread_id="thread_1", mode="chat")

    session = store.get_session("+15551234567")
    assert session is not None
    assert session["thread_id"] == "thread_1"


def test_store_approval_roundtrip(tmp_path):
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.create_run(run_id="run_1", sender="+15551234567", intent="task", state="awaiting_approval", cwd="/tmp", risk_level="execute")
    store.create_approval(
        request_id="req_1",
        run_id="run_1",
        summary="Need to run scaffold",
        command_preview="mkdir demo",
        expires_at="2099-01-01T00:00:00Z",
        sender="+15551234567",
    )

    pending = store.list_pending_approvals()
    assert len(pending) == 1
    assert pending[0]["request_id"] == "req_1"
    assert pending[0]["sender"] == "+15551234567"


def test_state_roundtrip(tmp_path):
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.set_state("last_rowid", "42")
    assert store.get_state("last_rowid") == "42"


def test_run_job_queue_claim_complete_roundtrip(tmp_path):
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.create_run(
        run_id="run_1",
        sender="+15551234567",
        intent="task",
        state="queued",
        cwd="/tmp",
        risk_level="execute",
    )
    store.enqueue_run_job(
        job_id="job_1",
        run_id="run_1",
        sender="+15551234567",
        phase="executor",
        attempt=1,
        payload={"request_id": "req_1"},
    )

    claimed = store.claim_next_run_job(worker_id="worker_1", lease_seconds=120)
    assert claimed is not None
    assert claimed["job_id"] == "job_1"
    assert claimed["status"] == "running"
    assert claimed["payload"]["request_id"] == "req_1"

    assert store.renew_run_job_lease(job_id="job_1", worker_id="worker_1", lease_seconds=120) is True
    assert store.complete_run_job(job_id="job_1", status="completed") is True
    jobs = store.list_run_jobs(run_id="run_1")
    assert jobs[0]["status"] == "completed"


def test_requeue_expired_run_jobs(tmp_path):
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.create_run(
        run_id="run_2",
        sender="+15551234567",
        intent="task",
        state="running",
        cwd="/tmp",
        risk_level="execute",
    )
    store.enqueue_run_job(
        job_id="job_2",
        run_id="run_2",
        sender="+15551234567",
        phase="executor",
        attempt=1,
        payload={},
        status="running",
    )

    # Force lease to be expired.
    conn = store._connect()
    with store._lock:
        conn.execute(
            "UPDATE run_jobs SET lease_owner='worker_x', lease_expires_at='2000-01-01T00:00:00', status='running' WHERE job_id='job_2'"
        )
        conn.commit()

    recovered = store.requeue_expired_run_jobs()
    assert recovered == 1
    jobs = store.list_run_jobs(run_id="run_2")
    assert jobs[0]["status"] == "queued"


def test_create_event_mirrors_to_csv_audit(tmp_path):
    class RecordingCsvLogger:
        def __init__(self) -> None:
            self.rows = []

        def append_event(self, event_row):
            self.rows.append(event_row)

    csv_logger = RecordingCsvLogger()
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path, csv_audit_logger=csv_logger)
    store.bootstrap()
    store.create_run(
        run_id="run_3",
        sender="+15551234567",
        intent="task",
        state="queued",
        cwd="/tmp/workspace",
        risk_level="execute",
        source_context={"channel": "mail"},
    )

    store.create_event(
        event_id="evt_3",
        run_id="run_3",
        step="executor",
        event_type="execution_started",
        payload={"attempt": 1, "status": "running", "snippet": "started"},
    )

    events = store.list_events_for_run("run_3", limit=10)
    assert len(events) == 1
    assert len(csv_logger.rows) == 1
    row = csv_logger.rows[0]
    assert row["event_id"] == "evt_3"
    assert row["run_id"] == "run_3"
    assert row["channel"] == "mail"
    assert row["workspace"] == "/tmp/workspace"
    assert row["attempt"] == 1
    assert row["status"] == "running"


def test_create_event_db_write_survives_csv_failure(tmp_path):
    class FailingCsvLogger:
        def append_event(self, _event_row):
            raise RuntimeError("csv append failed")

    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path, csv_audit_logger=FailingCsvLogger())
    store.bootstrap()
    store.create_run(
        run_id="run_4",
        sender="+15551234567",
        intent="task",
        state="queued",
        cwd="/tmp/workspace",
        risk_level="execute",
    )

    store.create_event(
        event_id="evt_4",
        run_id="run_4",
        step="executor",
        event_type="execution_started",
        payload={},
    )

    events = store.list_events_for_run("run_4", limit=10)
    assert len(events) == 1
    assert events[0]["event_id"] == "evt_4"


def test_healer_issue_claim_backoff_and_recovery(tmp_path):
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.upsert_healer_issue(
        issue_id="101",
        repo="owner/repo",
        title="Fix flaky test",
        body="tests/test_store.py failing",
        author="alice",
        labels=["healer:ready"],
        priority=10,
    )

    claimed = store.claim_next_healer_issue(worker_id="worker_a", lease_seconds=60)
    assert claimed is not None
    assert claimed["issue_id"] == "101"
    assert claimed["state"] == "claimed"

    store.set_healer_issue_state(
        issue_id="101",
        state="queued",
        backoff_until="2099-01-01T00:00:00+00:00",
        clear_lease=True,
    )
    assert store.claim_next_healer_issue(worker_id="worker_a", lease_seconds=60) is None

    # Force expired lease and ensure requeue scan recovers it.
    store.set_healer_issue_state(issue_id="101", state="claimed")
    conn = store._connect()
    with store._lock:
        conn.execute(
            "UPDATE healer_issues SET lease_owner='worker_a', lease_expires_at='2000-01-01T00:00:00', state='running' WHERE issue_id='101'"
        )
        conn.commit()
    recovered = store.requeue_expired_healer_issue_leases()
    assert recovered == 1
    issue = store.get_healer_issue("101")
    assert issue is not None
    assert issue["state"] == "queued"


def test_healer_locks_acquire_and_release(tmp_path):
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.upsert_healer_issue(
        issue_id="201",
        repo="owner/repo",
        title="Issue one",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=10,
    )
    store.upsert_healer_issue(
        issue_id="202",
        repo="owner/repo",
        title="Issue two",
        body="",
        author="bob",
        labels=["healer:ready"],
        priority=20,
    )

    ok = store.acquire_healer_lock(
        lock_key="path:src/apple_flow/store.py",
        granularity="path",
        issue_id="201",
        lease_owner="worker_a",
        lease_seconds=60,
    )
    assert ok is True

    conflict = store.acquire_healer_lock(
        lock_key="path:src/apple_flow/store.py",
        granularity="path",
        issue_id="202",
        lease_owner="worker_b",
        lease_seconds=60,
    )
    assert conflict is False

    released = store.release_healer_locks(issue_id="201")
    assert released == 1

    ok_after_release = store.acquire_healer_lock(
        lock_key="path:src/apple_flow/store.py",
        granularity="path",
        issue_id="202",
        lease_owner="worker_b",
        lease_seconds=60,
    )
    assert ok_after_release is True


def test_healer_lessons_roundtrip_and_stats(tmp_path):
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.upsert_healer_issue(
        issue_id="301",
        repo="owner/repo",
        title="Fix flaky lock",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=10,
    )
    store.create_healer_attempt(
        attempt_id="hat_301",
        issue_id="301",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["path:src/apple_flow/store.py"],
    )
    store.finish_healer_attempt(
        attempt_id="hat_301",
        state="failed",
        actual_diff_set=[],
        test_summary={},
        verifier_summary={},
        failure_class="lock_conflict",
        failure_reason="conflict",
    )
    attempts = store.list_recent_healer_attempts(limit=1)
    assert attempts[0]["failure_class"] == "lock_conflict"

    store.create_healer_lesson(
        lesson_id="lesson_1",
        issue_id="301",
        attempt_id="hat_301",
        lesson_kind="guardrail",
        scope_key="path:src/apple_flow/store.py",
        fingerprint="fp_1",
        problem_summary="Fix flaky lock",
        lesson_text="Keep changes scoped.",
        test_hint="Run tests/test_store.py",
        guardrail={"failure_class": "lock_conflict"},
        confidence=65,
        outcome="failure",
    )

    lessons = store.list_healer_lessons()
    assert len(lessons) == 1
    assert lessons[0]["guardrail"]["failure_class"] == "lock_conflict"

    updated = store.mark_healer_lessons_used(["lesson_1"])
    assert updated == 1
    stats = store.get_healer_lesson_stats()
    assert stats["total_lessons"] == 1
    assert stats["recently_used"] == 1
    assert stats["top_failure_classes"][0]["failure_class"] == "lock_conflict"


def test_scan_run_and_finding_roundtrip(tmp_path):
    db_path = tmp_path / "relay.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.create_scan_run(run_id="scan_1", dry_run=True)
    ok = store.finish_scan_run(
        run_id="scan_1",
        status="completed",
        summary={"findings_total": 2, "created_issues": []},
    )
    assert ok is True

    store.upsert_scan_finding(
        fingerprint="abc123",
        scan_type="pytest",
        severity="high",
        title="Test failing: tests/test_a.py::test_x",
        status="detected",
        payload={"selector": "tests/test_a.py::test_x"},
    )
    store.upsert_scan_finding(
        fingerprint="abc123",
        scan_type="pytest",
        severity="high",
        title="Test failing: tests/test_a.py::test_x",
        status="open",
        payload={"selector": "tests/test_a.py::test_x"},
        issue_number=77,
    )

    finding = store.get_scan_finding("abc123")
    assert finding is not None
    assert finding["status"] == "open"
    assert finding["issue_number"] == 77
    assert finding["payload"]["selector"] == "tests/test_a.py::test_x"
