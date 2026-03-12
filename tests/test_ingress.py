import sqlite3
import threading

from apple_flow.ingress import IMessageIngress


def test_latest_rowid_reads_max(tmp_path):
    db_path = tmp_path / "chat.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE message (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
        conn.execute("INSERT INTO message(text) VALUES ('a')")
        conn.execute("INSERT INTO message(text) VALUES ('b')")

    ingress = IMessageIngress(db_path)
    assert ingress.latest_rowid() == 2


def test_ingress_connection_can_be_reused_from_worker_thread(tmp_path):
    db_path = tmp_path / "chat.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT)")
        conn.execute(
            """
            CREATE TABLE message (
              ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
              handle_id INTEGER,
              destination_caller_id TEXT,
              text TEXT,
              date INTEGER,
              is_from_me INTEGER
            )
            """
        )
        conn.execute("INSERT INTO handle(ROWID, id) VALUES (1, '+15551234567')")
        conn.execute(
            "INSERT INTO message(handle_id, destination_caller_id, text, date, is_from_me) "
            "VALUES (1, NULL, 'thread-hop', 0, 0)"
        )

    ingress = IMessageIngress(db_path)
    assert ingress.latest_rowid() == 1

    rows: list = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            rows.extend(ingress.fetch_new())
        except Exception as exc:  # pragma: no cover - assertion below checks no exception
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert errors == []
    assert len(rows) == 1
    assert rows[0].text == "thread-hop"
