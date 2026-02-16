from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommandKind(str, Enum):
    CHAT = "chat"
    IDEA = "idea"
    PLAN = "plan"
    TASK = "task"
    PROJECT = "project"
    CLEAR_CONTEXT = "clear_context"
    APPROVE = "approve"
    DENY = "deny"
    STATUS = "status"


@dataclass(slots=True)
class ParsedCommand:
    kind: CommandKind
    payload: str


_PREFIX_TO_KIND = {
    "idea": CommandKind.IDEA,
    "plan": CommandKind.PLAN,
    "task": CommandKind.TASK,
    "project": CommandKind.PROJECT,
}


def parse_command(raw_text: str) -> ParsedCommand:
    text = raw_text.strip()
    lowered = text.lower()

    if lowered == "status":
        return ParsedCommand(kind=CommandKind.STATUS, payload="")

    if lowered in {"clear context", "new chat", "reset context"}:
        return ParsedCommand(kind=CommandKind.CLEAR_CONTEXT, payload="")

    if lowered.startswith("approve "):
        return ParsedCommand(kind=CommandKind.APPROVE, payload=text.split(" ", 1)[1].strip())

    if lowered.startswith("deny "):
        return ParsedCommand(kind=CommandKind.DENY, payload=text.split(" ", 1)[1].strip())

    for prefix, kind in _PREFIX_TO_KIND.items():
        marker = f"{prefix}:"
        if lowered.startswith(marker):
            return ParsedCommand(kind=kind, payload=text[len(marker):].strip())

    return ParsedCommand(kind=CommandKind.CHAT, payload=text)
