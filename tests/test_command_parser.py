from apple_flow.commanding import CommandKind, parse_command


def test_parse_prefixed_idea_command():
    parsed = parse_command("idea: build me a scraper")
    assert parsed.kind is CommandKind.IDEA
    assert parsed.payload == "build me a scraper"


def test_parse_approval_commands():
    approve = parse_command("approve 12345")
    deny = parse_command("deny req-9")

    assert approve.kind is CommandKind.APPROVE
    assert approve.payload == "12345"
    assert deny.kind is CommandKind.DENY
    assert deny.payload == "req-9"


def test_parse_fallback_to_chat():
    parsed = parse_command("hello there")
    assert parsed.kind is CommandKind.CHAT
    assert parsed.payload == "hello there"


def test_parse_clear_context_aliases():
    for raw in ["clear context", "new chat", "reset context"]:
        parsed = parse_command(raw)
        assert parsed.kind is CommandKind.CLEAR_CONTEXT
