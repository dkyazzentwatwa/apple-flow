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
