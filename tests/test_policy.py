from codex_relay.config import RelaySettings
from codex_relay.policy import PolicyEngine


def test_sender_allowlist_enforced():
    settings = RelaySettings(
        allowed_senders=["+15551234567"],
        allowed_workspaces=["/Users/cypher/Public/code"],
    )
    policy = PolicyEngine(settings)

    assert policy.is_sender_allowed("+15551234567")
    assert not policy.is_sender_allowed("+15550000000")


def test_workspace_allowlist_enforced():
    settings = RelaySettings(
        allowed_senders=["+15551234567"],
        allowed_workspaces=["/Users/cypher/Public/code", "/tmp/safe"],
    )
    policy = PolicyEngine(settings)

    assert policy.is_workspace_allowed("/Users/cypher/Public/code/codex-flow")
    assert not policy.is_workspace_allowed("/etc")


def test_sender_rate_limit():
    settings = RelaySettings(
        allowed_senders=["+15551234567"],
        allowed_workspaces=["/Users/cypher/Public/code"],
        max_messages_per_minute=2,
    )
    policy = PolicyEngine(settings)

    assert policy.is_under_rate_limit("+15551234567")
    assert policy.is_under_rate_limit("+15551234567")
    assert not policy.is_under_rate_limit("+15551234567")
