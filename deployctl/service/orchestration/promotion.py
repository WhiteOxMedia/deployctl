"""Promotion orchestration engine for the deployment control plane.

This engine handles promotion transitions for deployments. Right now it is
intentionally thin:

- load a deployment from the repository
- call the configured promotion-related adapters
- write the updated deployment back
- emit a stub operation-log entry
- return a PromotionResult DTO

It does not implement exposure or rollback. Those belong in
ExposureController and RollbackCoordinator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deployctl.adapters.promotion import PromotionAdapter
from deployctl.adapters.registry import RegistryAdapter
from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.errors import (
    DeploymentNotFoundError,
    PromotionError,
)
from deployctl.persistence.repository import DeploymentRepository


@dataclass(frozen=True)
class PromotionRequest:
    """One requested promotion attempt."""

    deployment_id: str
    reason: str
    target_artifact_ref: str | None = None


@dataclass(frozen=True)
class PromotionResult:
    """Outcome of a promotion attempt."""

    deployment_id: str
    successful: bool
    previous_status: str
    current_status: str
    reason: str
    promoted_to: str
    error: str | None = None
    steps: dict[str, Any] | None = None


class PromotionEngine:
    """Orchestrates promotion transitions for deployments.

    Public surface is deliberately small so it can be tested against a
    real DeploymentRepository without requiring the rest of the vertical
    slices to be wired yet.
    """

    def __init__(
        self,
        *,
        deployment_repository: DeploymentRepository,
        promotion: PromotionAdapter,
        registry: RegistryAdapter,
    ) -> None:
        self.deployment_repository = deployment_repository
        self.promotion = promotion
        self.registry = registry

    async def promote(self, request: PromotionRequest) -> PromotionResult:
        """Run one promotion attempt.

        Raises:
            DeploymentNotFoundError: if the deployment does not exist.
            PromotionError: if the promotion cannot proceed.
        """
        deployment = await self.deployment_repository.get_by_id(request.deployment_id)
        if deployment is None:
            raise DeploymentNotFoundError(
                message=f"deployment not found: {request.deployment_id}",
                details={"deployment_id": request.deployment_id},
            )

        previous_status = deployment.status
        promote_target = self._promotion_target(request, deployment)
        if promote_target is None:
            raise PromotionError(
                message=(
                    f"Promotion is not available for deployment "
                    f"{request.deployment_id}: no promote target"
                ),
                code="promotion_not_available",
                details={
                    "deployment_id": request.deployment_id,
                    "reason": "no promote target",
                },
            )

        steps: dict[str, Any] = {}
        try:
            steps["registry"] = await self._promote_registry(
                deployment, promote_target, request
            )
        except Exception as exc:
            raise PromotionError(
                message=(
                    f"Promotion restore step failed for "
                    f"deployment {request.deployment_id}: {exc}"
                ),
                code="promotion_restore_step_failed",
                details={
                    "deployment_id": request.deployment_id,
                    "reason": f"{type(exc).__name__}: {exc}",
                },
            ) from exc

        deployment.artifact_ref = promote_target
        deployment.status = "promoted"
        updated = await self.deployment_repository.save(deployment)
        self._emit_operation_log(
            deployment_id=request.deployment_id,
            previous_status=previous_status,
            current_status=updated.status,
            reason=request.reason,
            promote_target=promote_target,
        )

        return PromotionResult(
            deployment_id=request.deployment_id,
            successful=True,
            previous_status=previous_status,
            current_status=updated.status,
            reason=request.reason,
            promoted_to=promote_target,
            steps=steps,
        )

    # ------------------------------------------------------------------
    # Promotion decision helpers
    # ------------------------------------------------------------------

    def _promotion_target(
        self, request: PromotionRequest, deployment: Deployment
    ) -> str | None:
        if request.target_artifact_ref:
            return request.target_artifact_ref
        return deployment.artifact_ref or None

    async def _promote_registry(
        self,
        deployment: Deployment,
        promote_target: str,
        request: PromotionRequest,
    ) -> Any:
        return self.registry.promote(
            serving_path_id=deployment.id,
            new_serving=promote_target,
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
        promote_target: str,
    ) -> None:
        # Operation logging is a future slice. This stub exists so the
        # coordinator shape is stable even before that repository is real.
        _operation_log_entry = {
            "deployment_id": deployment_id,
            "previous_status": previous_status,
            "current_status": current_status,
            "reason": reason,
            "promote_target": promote_target,
        }
        return
