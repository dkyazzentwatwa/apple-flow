import sqlite3

from apple_flow.ingress import IMessageIngress


def test_fetch_new_returns_none_when_strict_filter_required_but_empty_allowlist(tmp_path):
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
            "INSERT INTO message(handle_id, destination_caller_id, text, date, is_from_me) VALUES (1, NULL, 'hello', 0, 0)"
        )

    ingress = IMessageIngress(db_path)
    rows = ingress.fetch_new(sender_allowlist=[], require_sender_filter=True)

    assert rows == []
