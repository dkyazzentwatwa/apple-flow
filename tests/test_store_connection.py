"""Tests for SQLiteStore connection caching and thread safety."""

import threading
from pathlib import Path

from apple_flow.store import SQLiteStore


def test_store_connection_caching(tmp_path: Path):
    """Verify that the store reuses the same connection."""
    db_path = tmp_path / "test.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    # First connection
    conn1 = store._connect()

    # Second connection should be the same object
    conn2 = store._connect()

    assert conn1 is conn2

    store.close()


def test_store_close_and_reconnect(tmp_path: Path):
    """Verify that close() allows reconnection."""
    db_path = tmp_path / "test.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    conn1 = store._connect()
    store.close()

    # After close, should get a new connection
    conn2 = store._connect()
    assert conn1 is not conn2

    store.close()


def test_store_thread_safety(tmp_path: Path):
    """Verify that the store is thread-safe."""
    db_path = tmp_path / "test.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    errors: list[Exception] = []
    results: list[str | None] = []

    def writer(thread_id: int) -> None:
        try:
            for i in range(10):
                store.set_state(f"key_{thread_id}_{i}", f"value_{i}")
        except Exception as e:
            errors.append(e)

    def reader(thread_id: int) -> None:
        try:
            for i in range(10):
                result = store.get_state(f"key_{thread_id}_{i}")
                results.append(result)
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(5):
        t = threading.Thread(target=writer, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"

    # Verify data was written
    for i in range(5):
        for j in range(10):
            value = store.get_state(f"key_{i}_{j}")
            assert value == f"value_{j}"

    store.close()


def test_store_indexes_created(tmp_path: Path):
    """Verify that indexes are created during bootstrap."""
    db_path = tmp_path / "test.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    conn = store._connect()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
    indexes = [row[0] for row in cursor.fetchall()]

    expected_indexes = [
        "idx_messages_sender",
        "idx_approvals_status",
        "idx_runs_sender",
        "idx_events_run_id",
    ]

    for idx in expected_indexes:
        assert idx in indexes, f"Missing index: {idx}"

    store.close()


def test_store_approval_with_sender(tmp_path: Path):
    """Verify that approvals store sender information."""
    db_path = tmp_path / "test.db"
    store = SQLiteStore(db_path)
    store.bootstrap()

    store.create_run(
        run_id="run_1",
        sender="+15551234567",
        intent="task",
        state="planning",
        cwd="/tmp",
        risk_level="execute",
    )

    store.create_approval(
        request_id="req_1",
        run_id="run_1",
        summary="Test approval",
        command_preview="echo hello",
        expires_at="2099-01-01T00:00:00Z",
        sender="+15551234567",
    )

    approval = store.get_approval("req_1")
    assert approval is not None
    assert approval["sender"] == "+15551234567"

    store.close()
