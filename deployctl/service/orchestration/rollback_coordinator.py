"""Rollback orchestration coordinator for the deployment control plane.

This coordinator handles rollback transitions for deployments. Right now it is
intentionally thin:

- load a deployment from the repository
- optionally consult readiness (non-blocking)
- validate that a rollback target exists
- call the configured rollback-related adapters
- write the updated deployment back
- emit a stub operation-log entry
- return a RollbackResult DTO

Rollback may consult readiness for context but does not block on it.
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
from deployctl.domain.readiness import ReadinessRecord
from deployctl.persistence.repository import DeploymentRepository
from deployctl.service.orchestration.readiness_controller import ReadinessController


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
    readiness_status: str | None = None


class RollbackCoordinator:
    """Orchestrates rollback transitions for deployments.

    Public surface is deliberately small so it can be tested against a
    real DeploymentRepository without requiring the rest of the vertical
    slices to be wired yet.

    Rollback may consult readiness for context but does not block on it.
    """

    def __init__(
        self,
        *,
        deployment_repository: DeploymentRepository,
        registry: RegistryAdapter,
        readiness_controller: ReadinessController | None = None,
    ) -> None:
        self.deployment_repository = deployment_repository
        self.registry = registry
        self.readiness_controller = readiness_controller

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

        readiness = await self._readiness_snapshot(request.deployment_id)
        self._emit_operation_log(
            deployment_id=request.deployment_id,
            previous_status=previous_status,
            current_status=updated.status,
            reason=request.reason,
            restore_target=restore_target,
            readiness_status=readiness.status.value if readiness is not None else None,
        )

        return RollbackResult(
            deployment_id=request.deployment_id,
            successful=True,
            previous_status=previous_status,
            current_status=updated.status,
            reason=request.reason,
            restored_to=restore_target,
            steps=steps,
            readiness_status=readiness.status.value if readiness is not None else None,
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

    async def _readiness_snapshot(self, deployment_id: str) -> ReadinessRecord | None:
        """Return the latest readiness record if readiness is wired in.

        Rollback does not block on readiness, but it still snapshots the current
        decision so the result can carry the readiness context.
        """
        controller = self.readiness_controller
        if controller is None:
            return None

        return await controller.get_status(deployment_id=deployment_id)

    def _emit_operation_log(
        self,
        *,
        deployment_id: str,
        previous_status: str,
        current_status: str,
        reason: str,
        restore_target: str,
        readiness_status: str | None = None,
    ) -> None:
        # Operation logging is a future slice. This stub exists so the
        # coordinator shape is stable even before that repository is real.
        _operation_log_entry = {
            "deployment_id": deployment_id,
            "previous_status": previous_status,
            "current_status": current_status,
            "reason": reason,
            "restore_target": restore_target,
            "readiness_status": readiness_status,
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
