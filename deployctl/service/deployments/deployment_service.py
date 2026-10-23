"""Deployment service implementation (first vertical slice stub)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.errors import (
    DeploymentDuplicateError,
    DeploymentIntentError,
    DeploymentNotFoundError,
)
from deployctl.persistence.repository import DeploymentRepository


class DeploymentService:
    """Deployment use-case orchestration.

    This implements the first vertical slice:
    - Deployment creation
    - Deployment retrieval

    It depends on a DeploymentRepository implementation. Until the persistence
    layer is wired, this remains authoritarian about its contract and raises
    domain errors for invalid input.

    The methods are coroutines rather than synchronous wrappers around
    ``asyncio.run``: the API handlers are ``async def`` and share the
    application's event loop, so a repository connection can be reused across
    requests instead of being tied to a throwaway loop per request.
    """

    def __init__(self, *, deployment_repository: DeploymentRepository) -> None:
        self._deployment_repository = deployment_repository

    async def create_deployment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a deployment from an API payload.

        This is the first endpoint-backed use case. It validates the minimum
        intent fields and persists a placeholder deployment aggregate.
        """
        description = payload.get("description")
        artifact_ref = payload.get("artifact_ref")

        if not description or not isinstance(description, str):
            raise DeploymentIntentError(
                message="description must be a non-empty string",
                details={"field": "description", "value": description},
            )
        if not artifact_ref or not isinstance(artifact_ref, str):
            raise DeploymentIntentError(
                message="artifact_ref must be a non-empty string",
                details={"field": "artifact_ref", "value": artifact_ref},
            )

        deployment_id = payload.get("deployment_id") or self._generate_deployment_id()
        existing = await self._deployment_repository.get_by_id(deployment_id)
        if existing is not None:
            raise DeploymentDuplicateError(
                message=f"deployment already exists: {deployment_id}",
                details={"key": deployment_id, "existing_id": deployment_id},
            )

        deployment = Deployment(
            id=deployment_id,
            description=description,
            artifact_ref=artifact_ref,
            status="planned",
            created_at=datetime.now(UTC).isoformat(),
        )

        saved = await self._deployment_repository.save(deployment)
        return self._deployment_to_payload(saved)

    async def get_deployment(self, deployment_id: str) -> dict[str, Any]:
        """Retrieve a deployment by id."""
        deployment = await self._deployment_repository.get_by_id(deployment_id)
        if deployment is None:
            raise DeploymentNotFoundError(
                message=f"deployment not found: {deployment_id}",
                details={"deployment_id": deployment_id},
            )
        return self._deployment_to_payload(deployment)

    def _generate_deployment_id(self) -> str:
        import uuid

        return f"deploy-{uuid.uuid4().hex[:12]}"

    def _deployment_to_payload(self, deployment: Deployment) -> dict[str, Any]:
        return {
            "deployment_id": deployment.id,
            "description": deployment.description,
            "artifact_ref": deployment.artifact_ref,
            "status": deployment.status,
            "created_at": deployment.created_at,
        }
