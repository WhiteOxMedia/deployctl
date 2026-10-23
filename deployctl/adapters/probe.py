"""Probe adapter interface.

This is a contract for external probing/checking systems. No real logic yet.
"""

from __future__ import annotations

from typing import Any, Protocol


class ProbeAdapter(Protocol):
    """Contract for executing a readiness/observation probe."""

    def execute(
        self,
        *,
        deployment_id: str,
        scope_id: str | None = None,
        source_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def resolve_source(self, *, source_id: str) -> dict[str, Any]: ...
