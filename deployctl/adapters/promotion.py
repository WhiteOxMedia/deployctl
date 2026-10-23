"""Promotion adapter interface.

This is a contract for external promotion systems. No real logic yet.
"""

from __future__ import annotations

from typing import Any, Protocol


class PromotionAdapter(Protocol):
    """Contract for promoting a deployment candidate."""

    def promote(
        self,
        *,
        serving_path_id: str,
        new_serving: str,
        deployment_run_id: str | None = None,
    ) -> dict[str, Any]: ...

    def status(self, *, serving_path_id: str) -> dict[str, Any]: ...
