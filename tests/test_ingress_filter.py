import sqlite3

from codex_relay.ingress import IMessageIngress


def _create_messages_db(path):
    with sqlite3.connect(path) as conn:
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
        conn.execute("INSERT INTO handle(ROWID, id) VALUES (2, '+15557654321')")
        conn.execute("INSERT INTO message(handle_id, destination_caller_id, text, date, is_from_me) VALUES (1, NULL, 'mine', 0, 0)")
        conn.execute("INSERT INTO message(handle_id, destination_caller_id, text, date, is_from_me) VALUES (2, NULL, 'other', 0, 0)")


def test_fetch_new_can_filter_by_allowlist(tmp_path):
    db_path = tmp_path / "chat.db"
    _create_messages_db(db_path)

    ingress = IMessageIngress(db_path)
    rows = ingress.fetch_new(sender_allowlist=["+15551234567"])

    assert len(rows) == 1
    assert rows[0].sender == "+15551234567"
    assert rows[0].text == "mine"
