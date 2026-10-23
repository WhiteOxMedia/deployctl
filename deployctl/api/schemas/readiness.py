"""Readiness request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReadinessResponse(BaseModel):
    """Current readiness for a single deployment."""

    deployment_id: str
    status: str
    details: dict[str, Any] | None
    observed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProbeRequest(BaseModel):
    """Optional probe override parameters."""

    scope_id: str | None = None
    source_id: str | None = None
    params: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class ProbeResponse(BaseModel):
    """Result of a readiness probe evaluation."""

    deployment_id: str
    status: str
    healthy: bool
    details: dict[str, Any] | None
    observed_at: datetime

    model_config = ConfigDict(from_attributes=True)
