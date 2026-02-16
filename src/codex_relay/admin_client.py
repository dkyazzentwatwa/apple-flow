"""Admin API client for Codex Relay."""

from __future__ import annotations

from typing import Any

import httpx


class AdminClient:
    """Client for interacting with the Codex Relay admin API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8787", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def pending_approvals(self) -> list[dict[str, Any]]:
        """Get list of pending approval requests."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/approvals/pending")
            response.raise_for_status()
            return response.json()

    def override_approval(self, request_id: str, status: str) -> dict[str, Any]:
        """Override an approval request status."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/approvals/{request_id}/override",
                json={"status": status},
            )
            response.raise_for_status()
            return response.json()

    def list_sessions(self) -> list[dict[str, Any]]:
        """Get list of active sessions."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/sessions")
            response.raise_for_status()
            return response.json()

    def audit_events(self, limit: int = 200) -> list[dict[str, Any]]:
        """Get recent audit events."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/events", params={"limit": limit})
            response.raise_for_status()
            return response.json()

    def health(self) -> dict[str, Any]:
        """Check API health."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
