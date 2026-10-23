"""Deployment DTO mapping."""

from __future__ import annotations

from typing import Any

from deployctl.api.schemas.deployments import DeploymentResponse
from deployctl.domain.aggregate.deployment import Deployment


def deployment_to_response(deployment: Deployment) -> DeploymentResponse:
    """Map a Deployment aggregate to its API response representation."""
    return DeploymentResponse(
        deployment_id=deployment.id,
        description=deployment.description,
        artifact_ref=deployment.artifact_ref,
        status=deployment.status,
        created_at=deployment.created_at,
    )


def response_to_create_payload(response: DeploymentResponse) -> dict[str, Any]:
    """Convert a response representation back into a create payload dict."""
    return {
        "deployment_id": response.deployment_id,
        "description": response.description,
        "artifact_ref": response.artifact_ref,
        "metadata": response.metadata if hasattr(response, "metadata") else {},
    }
