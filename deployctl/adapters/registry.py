"""Registry adapter interface.

This is a contract for external serving-path/origin registry systems. No real
logic yet.
"""

from __future__ import annotations

from typing import Any, Protocol


class RegistryAdapter(Protocol):
    """Contract for serving-path/origin registry operations."""

    def configure(
        self,
        *,
        serving_path_id: str,
        current_serving: str,
        previous_serving: str | None = None,
    ) -> dict[str, Any]: ...

    def promote(
        self,
        *,
        serving_path_id: str,
        new_serving: str,
        deployment_run_id: str | None = None,
    ) -> dict[str, Any]: ...

    def restore(
        self,
        *,
        serving_path_id: str,
        previous_serving: str,
        deployment_run_id: str | None = None,
    ) -> dict[str, Any]: ...

    def status(self, *, serving_path_id: str) -> dict[str, Any]: ...
