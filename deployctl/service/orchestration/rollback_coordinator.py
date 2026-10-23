"""Rollback orchestration coordinator for the deployment control plane.

This coordinator handles rollback transitions for deployments. Right now it is
intentionally thin:

- load a deployment from the repository
- validate that a rollback target exists
- call the configured rollback-related adapters
- write the updated deployment back
- emit a stub operation-log entry
- return a RollbackResult DTO

It does not implement promotion or exposure. Those belong in
PromotionEngine and ExposureController.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deployctl.adapters.registry import RegistryAdapter
from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.errors import (
    DeploymentNotFoundError,
    RollbackAnchorError,
    RollbackNotFoundError,
)
from deployctl.persistence.repository import DeploymentRepository


@dataclass(frozen=True)
class RollbackRequest:
    """One requested rollback attempt."""

    deployment_id: str
    reason: str
    target_artifact_ref: str | None = None


@dataclass(frozen=True)
class RollbackResult:
    """Outcome of a rollback attempt."""

    deployment_id: str
    successful: bool
    previous_status: str
    current_status: str
    reason: str
    restored_to: str
    error: str | None = None
    steps: dict[str, Any] | None = None


class RollbackCoordinator:
    """Orchestrates rollback transitions for deployments.

    Public surface is deliberately small so it can be tested against a
    real DeploymentRepository without requiring the rest of the vertical
    slices to be wired yet.
    """

    def __init__(
        self,
        *,
        deployment_repository: DeploymentRepository,
        registry: RegistryAdapter,
    ) -> None:
        self.deployment_repository = deployment_repository
        self.registry = registry

    async def rollback(self, request: RollbackRequest) -> RollbackResult:
        """Run one rollback attempt.

        Raises:
            DeploymentNotFoundError: if the deployment does not exist.
            RollbackNotFoundError: if there is nothing to roll back to.
            RollbackAnchorError: if the rollback target is unusable.
        """
        deployment = await self.deployment_repository.get_by_id(request.deployment_id)
        if deployment is None:
            raise DeploymentNotFoundError(
                message=f"deployment not found: {request.deployment_id}",
                details={"deployment_id": request.deployment_id},
            )

        previous_status = deployment.status
        restore_target = self._rollback_target(request, deployment)
        if restore_target is None:
            raise _make_rollback_not_found(
                request.deployment_id,
                "no restore target",
            )

        restore_target = self._validate_rollback_target(request, restore_target)

        steps: dict[str, Any] = {}
        try:
            steps["registry"] = await self._restore_registry(
                deployment, restore_target, request
            )
        except Exception as exc:
            raise RollbackAnchorError(
                deployment_id=request.deployment_id,
                reason=f"rollback restore step failed: {exc}",
            ) from exc

        deployment.artifact_ref = restore_target
        deployment.status = "rolled_back"
        updated = await self.deployment_repository.save(deployment)
        self._emit_operation_log(
            deployment_id=request.deployment_id,
            previous_status=previous_status,
            current_status=updated.status,
            reason=request.reason,
            restore_target=restore_target,
        )

        return RollbackResult(
            deployment_id=request.deployment_id,
            successful=True,
            previous_status=previous_status,
            current_status=updated.status,
            reason=request.reason,
            restored_to=restore_target,
            steps=steps,
        )

    # ------------------------------------------------------------------
    # Rollback decision helpers
    # ------------------------------------------------------------------

    def _rollback_target(
        self, request: RollbackRequest, deployment: Deployment
    ) -> str | None:
        if request.target_artifact_ref:
            return request.target_artifact_ref
        return deployment.artifact_ref or None

    def _validate_rollback_target(
        self, request: RollbackRequest, restore_target: str
    ) -> str:
        if not restore_target:
            raise RollbackAnchorError(
                deployment_id=request.deployment_id,
                reason="rollback target is empty",
            )
        return restore_target

    async def _restore_registry(
        self,
        deployment: Deployment,
        restore_target: str,
        request: RollbackRequest,
    ) -> Any:
        return self.registry.restore(
            serving_path_id=deployment.id,
            previous_serving=restore_target,
            deployment_run_id=deployment.id,
        )

    # ------------------------------------------------------------------
    # Observability stub
    # ------------------------------------------------------------------

    def _emit_operation_log(
        self,
        *,
        deployment_id: str,
        previous_status: str,
        current_status: str,
        reason: str,
        restore_target: str,
    ) -> None:
        # Operation logging is a future slice. This stub exists so the
        # coordinator shape is stable even before that repository is real.
        _operation_log_entry = {
            "deployment_id": deployment_id,
            "previous_status": previous_status,
            "current_status": current_status,
            "reason": reason,
            "restore_target": restore_target,
        }
        return


def _make_rollback_not_found(deployment_id: str, reason: str) -> Exception:
    """Build a rollback-not-found failure exception for this coordinator.

    This helper exists so the coordinator does not depend on a particular
    `RollbackNotFoundError` constructor signature here and now.
    """
    return RollbackNotFoundError(
        deployment_id=deployment_id,
        reason=reason,
    )
