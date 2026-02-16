from codex_relay.store import SQLiteStore


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
