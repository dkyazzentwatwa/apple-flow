from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RunState(str, Enum):
    """States for task/project runs."""

    RECEIVED = "received"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    CHECKPOINTED = "checkpointed"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    """Status values for approval requests."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass(slots=True)
class InboundMessage:
    id: str
    sender: str
    text: str
    received_at: str
    is_from_me: bool
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ApprovalRequest:
    request_id: str
    run_id: str
    summary: str
    command_preview: str
    expires_at: str
    status: str = "pending"
