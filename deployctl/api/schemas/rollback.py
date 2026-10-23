"""Rollback request/response schemas.

These schemas mirror the shape used by RollbackCoordinator.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RollbackRequest(BaseModel):
    reason: str
    target_artifact_ref: str | None = None


class RollbackResponse(BaseModel):
    deployment_id: str
    successful: bool
    previous_status: str
    current_status: str
    reason: str
    restored_to: str
    error: str | None = None
    steps: dict[str, Any] | None = None


rollback = RollbackResponse
