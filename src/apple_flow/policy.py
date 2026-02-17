from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import RelaySettings


class PolicyEngine:
    def __init__(self, settings: RelaySettings):
        self.settings = settings
        self._sender_windows: dict[str, deque[datetime]] = defaultdict(deque)

    def is_sender_allowed(self, sender: str) -> bool:
        if not self.settings.allowed_senders:
            return False
        return sender in self.settings.allowed_senders

    def is_workspace_allowed(self, workspace: str) -> bool:
        candidate = Path(workspace).resolve()
        for allowed in self.settings.allowed_workspaces:
            allowed_path = Path(allowed).resolve()
            if candidate == allowed_path or allowed_path in candidate.parents:
                return True
        return False

    def is_under_rate_limit(self, sender: str, now: datetime | None = None) -> bool:
        if self.settings.max_messages_per_minute <= 0:
            return True

        current = now or datetime.now(UTC)
        window_start = current - timedelta(minutes=1)
        bucket = self._sender_windows[sender]
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= self.settings.max_messages_per_minute:
            return False

        bucket.append(current)
        return True
