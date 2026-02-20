"""Protocol interfaces for Apple Flow components.

These protocols define the interfaces that store, connector, and egress
components must implement, enabling proper type checking and easier testing.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StoreProtocol(Protocol):
    """Protocol for persistent storage backends."""

    def bootstrap(self) -> None:
        """Initialize database schema."""
        ...

    def upsert_session(self, sender: str, thread_id: str, mode: str) -> None:
        """Create or update a session for a sender."""
        ...

    def get_session(self, sender: str) -> dict[str, Any] | None:
        """Get session data for a sender."""
        ...

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        ...

    def record_message(
        self, message_id: str, sender: str, text: str, received_at: str, dedupe_hash: str
    ) -> bool:
        """Record an inbound message. Returns True if newly inserted."""
        ...

    def create_run(
        self, run_id: str, sender: str, intent: str, state: str, cwd: str, risk_level: str
    ) -> None:
        """Create a new run record."""
        ...

    def update_run_state(self, run_id: str, state: str) -> None:
        """Update the state of an existing run."""
        ...

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get run data by ID."""
        ...

    def create_approval(
        self,
        request_id: str,
        run_id: str,
        summary: str,
        command_preview: str,
        expires_at: str,
        sender: str,
    ) -> None:
        """Create an approval request."""
        ...

    def get_approval(self, request_id: str) -> dict[str, Any] | None:
        """Get approval data by request ID."""
        ...

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        """List all pending approval requests."""
        ...

    def resolve_approval(self, request_id: str, status: str) -> bool:
        """Resolve an approval request. Returns True if updated."""
        ...

    def create_event(
        self, event_id: str, run_id: str, step: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        """Create an audit event."""
        ...

    def list_events(self, limit: int = 200) -> list[dict[str, Any]]:
        """List recent events."""
        ...

    def set_state(self, key: str, value: str) -> None:
        """Set a key-value state entry."""
        ...

    def get_state(self, key: str) -> str | None:
        """Get a key-value state entry."""
        ...

    def close(self) -> None:
        """Close database connections."""
        ...


@runtime_checkable
class ConnectorProtocol(Protocol):
    """Protocol for AI backend connectors."""

    def ensure_started(self) -> None:
        """Ensure the backend process is running."""
        ...

    def get_or_create_thread(self, sender: str) -> str:
        """Get or create a conversation thread for a sender."""
        ...

    def reset_thread(self, sender: str) -> str:
        """Reset the thread for a sender, returning the new thread ID."""
        ...

    def run_turn(self, thread_id: str, prompt: str) -> str:
        """Run a conversation turn and return the response."""
        ...

    def shutdown(self) -> None:
        """Gracefully shut down the backend process."""
        ...


@runtime_checkable
class EgressProtocol(Protocol):
    """Protocol for outbound message handlers."""

    def send(self, recipient: str, text: str) -> None:
        """Send a message to a recipient."""
        ...

    def was_recent_outbound(self, sender: str, text: str) -> bool:
        """Check if a message was recently sent (for echo detection)."""
        ...

    def mark_outbound(self, recipient: str, text: str) -> None:
        """Mark a message as recently sent."""
        ...
