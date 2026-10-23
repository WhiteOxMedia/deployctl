"""Orchestration layer for deployctl."""

from __future__ import annotations

from typing import Any

from deployctl.service.orchestration.promotion_engine import (
    PromotionEngine,
    PromotionEntry,
    PromotionResult,
)


class OrchestrationOrchestrator:
    """Top-level orchestration composition root.

    This exists so the service layer can stand up a single orchestration
    entry point without importing every implementation.
    """

    def __init__(self) -> None:
        self._commands: list[Any] = []

    async def promote(self, entry: PromotionEntry) -> PromotionResult:
        """Run a promotion through PromotionEngine.

        This is a stub until the real engine is wired with a repository and
        the configured adapters.
        """
        raise NotImplementedError


__all__ = [
    "ExposureController",
    "ExposureRequest",
    "ExposureResult",
    "PromotionEngine",
    "PromotionEntry",
    "PromotionResult",
    "RollbackCoordinator",
    "RollbackRequest",
    "RollbackResult",
]
