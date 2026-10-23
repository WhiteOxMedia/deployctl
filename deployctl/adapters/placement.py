"""Placement adapter interface.

This is a contract for external placement systems. No real logic yet.
"""

from __future__ import annotations

from typing import Any, Protocol


class PlacementAdapter(Protocol):
    """Contract for placing and introspecting a deployment candidate."""

    def place(
        self,
        *,
        deployment_id: str,
        run_id: str,
        artifact_ref: str,
        target_environment: str | None = None,
        resource_profile: str | None = None,
        routing_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def status(self, *, deployment_id: str, run_id: str) -> dict[str, Any]: ...

    def teardown(self, *, deployment_id: str, run_id: str) -> dict[str, Any]: ...
