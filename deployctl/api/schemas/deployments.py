"""Deployment request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DeploymentCreateRequest(BaseModel):
    deployment_id: str | None = None
    description: str
    artifact_ref: str
    metadata: dict[str, Any] = {}


class DeploymentResponse(BaseModel):
    deployment_id: str
    description: str
    artifact_ref: str
    status: str
    created_at: str


deployments = DeploymentResponse
