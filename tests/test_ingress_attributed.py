import sqlite3

from apple_flow.ingress import IMessageIngress


def test_fetch_new_falls_back_to_attributed_body_when_text_is_empty(tmp_path):
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
              attributedBody BLOB,
              date INTEGER,
              is_from_me INTEGER
            )
            """
        )
        conn.execute("INSERT INTO handle(ROWID, id) VALUES (1, '+15551234567')")
        blob = b"\x04\x0bstreamtyped\x08NSString\x01\x95\x84\x01\x2bprelay: status\x86\x84"
        conn.execute(
            "INSERT INTO message(handle_id, destination_caller_id, text, attributedBody, date, is_from_me) VALUES (1, NULL, NULL, ?, 0, 0)",
            (blob,),
        )

    ingress = IMessageIngress(db_path)
    rows = ingress.fetch_new()

    assert len(rows) == 1
    assert rows[0].text == "relay: status"
