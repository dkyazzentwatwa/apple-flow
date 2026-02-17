from apple_flow.egress import IMessageEgress


def test_suppresses_duplicate_outbound_within_window(monkeypatch):
    sent_calls = []

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    egress = IMessageEgress(suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send("+15551234567", "Hello world")
    egress.send("+15551234567", "Hello world")

    assert len(sent_calls) == 1

