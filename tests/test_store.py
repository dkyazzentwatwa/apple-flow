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

    runs = store.list_scan_runs(limit=5)
    assert runs and runs[0]["run_id"] == "scan_1"
    findings = store.list_scan_findings(limit=5)
    assert findings and findings[0]["fingerprint"] == "abc123"
