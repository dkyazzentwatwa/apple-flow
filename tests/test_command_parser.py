import pytest

from apple_flow.commanding import CommandKind, is_likely_mutating, parse_command


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


@pytest.mark.parametrize("text", [
    "create a Python file called hello.py",
    "write a script to parse CSV files",
    "generate a migration for the database",
    "deploy the app to production",
    "delete the old repo",
    "refactor the module to use async",
    "install the package dependencies",
    "run the tests for this project",
    "commit and push the code",
])
def test_is_likely_mutating_true(text):
    assert is_likely_mutating(text) is True


@pytest.mark.parametrize("text", [
    "write me a haiku about autumn",
    "explain how git rebase works",
    "what is the meaning of life?",
    "how do I center a div?",
    "tell me a joke",
    "summarize this paragraph",
    "what files are in the workspace?",
])
def test_is_likely_mutating_false(text):
    assert is_likely_mutating(text) is False
