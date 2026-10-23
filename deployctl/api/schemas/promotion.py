"""Promotion request/response schemas.

These schemas mirror the shape used by PromotionEngine and the
RollbackCoordinator-style DTOs where beneficial, but they are
independent API boundaries.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PromotionRequest(BaseModel):
    reason: str


class PromotionResponse(BaseModel):
    deployment_id: str
    successful: bool
    previous_status: str
    current_status: str
    reason: str
    promoted_to: str
    error: str | None = None
    steps: dict[str, Any] | None = None
