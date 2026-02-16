import sqlite3

from codex_relay.ingress import IMessageIngress


def test_latest_rowid_reads_max(tmp_path):
    db_path = tmp_path / "chat.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE message (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
        conn.execute("INSERT INTO message(text) VALUES ('a')")
        conn.execute("INSERT INTO message(text) VALUES ('b')")

    ingress = IMessageIngress(db_path)
    assert ingress.latest_rowid() == 2
