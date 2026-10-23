"""Promotion orchestration engine for the deployment control plane.

This is the first real controller implementation. It is intentionally thin:

- load a deployment from the repository
- ask the domain state machine whether promotion is legal
- call the configured adapters in the expected order
- write the updated deployment back
- emit a stub operation-log entry
- return a PromotionResult DTO

It does not implement exposure or rollback flows. Those belong in
ExposureController and RollbackCoordinator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The adapter contracts already live in the adapters package.
from deployctl.adapters.artifact import ArtifactAdapter
from deployctl.adapters.exposure import ExposureAdapter
from deployctl.adapters.placement import PlacementAdapter
from deployctl.adapters.registry import RegistryAdapter
from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.errors import DeploymentNotFoundError, PromotionError
from deployctl.domain.state_machine import DomainStateMachine
from deployctl.persistence.repository import DeploymentRepository


class PromotionNotAllowedError(PromotionError):
    """Raised when a promotion attempt is not allowed by the domain rules."""

    def __init__(
        self,
        message: str,
        *,
        deployment_id: str,
        current_status: str,
        target_status: str,
        reason: str,
    ) -> None:
        super().__init__(
            message=message,
            code="promotion_not_allowed",
            details={
                "deployment_id": deployment_id,
                "current_status": current_status,
                "target_status": target_status,
                "reason": reason,
            },
        )


class PromotionStepError(PromotionError):
    """Raised when a promotion adapter step fails."""

    def __init__(
        self,
        message: str,
        *,
        deployment_id: str,
        current_status: str,
        target_status: str,
        reason: str,
        step_failure: str,
    ) -> None:
        super().__init__(
            message=message,
            code="promotion_step_failed",
            details={
                "deployment_id": deployment_id,
                "current_status": current_status,
                "target_status": target_status,
                "reason": reason,
                "step_failure": step_failure,
            },
        )


@dataclass(frozen=True)
class PromotionEntry:
    """One requested promotion attempt."""

    deployment_id: str
    reason: str
    target_status: str | None = None


@dataclass(frozen=True)
class PromotionResult:
    """Outcome of a promotion attempt."""

    deployment_id: str
    successful: bool
    previous_status: str
    current_status: str
    reason: str
    error: str | None = None
    steps: dict[str, Any] | None = None


class PromotionEngine:
    """Orchestrates a promotion through the deployment lifecycle.

    Public surface is deliberately small so it can be tested against a
    real DeploymentRepository without requiring the rest of the vertical
    slices to be wired yet.
    """

    def __init__(
        self,
        *,
        deployment_repository: DeploymentRepository,
        placement: PlacementAdapter,
        exposure: ExposureAdapter,
        artifact: ArtifactAdapter,
        registry: RegistryAdapter,
        state_machine: DomainStateMachine,
    ) -> None:
        self.deployment_repository = deployment_repository
        self.placement = placement
        self.exposure = exposure
        self.artifact = artifact
        self.registry = registry
        self.state_machine = state_machine

    async def promote(self, entry: PromotionEntry) -> PromotionResult:
        """Run one promotion attempt.

        Raises:
            DeploymentNotFoundError: if the deployment does not exist.
            PromotionNotAllowedError: if the domain state machine forbids it.
        """
        return await self._promote(entry)

    async def _promote(self, entry: PromotionEntry) -> PromotionResult:
        """Run one promotion attempt.

        Raises:
            DeploymentNotFoundError: if the deployment does not exist.
            PromotionNotAllowedError: if the domain state machine forbids it.
        """
        deployment = await self.deployment_repository.get_by_id(entry.deployment_id)
        if deployment is None:
            raise DeploymentNotFoundError(
                message=f"deployment not found: {entry.deployment_id}",
                details={"deployment_id": entry.deployment_id},
            )

        previous_status = deployment.status
        target = entry.target_status or self.state_machine.promotion_target(
            previous_status
        )
        if target is None:
            raise PromotionNotAllowedError(
                message=f"promotion not allowed from status {previous_status!r}",
                deployment_id=entry.deployment_id,
                current_status=previous_status,
                target_status=target,
                reason=entry.reason,
            )

        # Ask the domain state machine whether we can move to the target.
        if not self.state_machine.can_transition(previous_status, target):
            raise PromotionNotAllowedError(
                message=(
                    f"domain state machine forbids {previous_status!r} -> {target!r}"
                ),
                deployment_id=entry.deployment_id,
                current_status=previous_status,
                target_status=target,
                reason=entry.reason,
            )

        steps: dict[str, Any] = {}
        try:
            steps["artifact"] = await self._resolve_artifact(deployment)
            steps["placement"] = await self._place(deployment, entry)
            steps["exposure"] = self._expose(deployment, target)
            steps["registry"] = self._update_registry(deployment, target, entry)
        except Exception as exc:
            raise PromotionStepError(
                message=f"promotion step failed for {entry.deployment_id!r}",
                deployment_id=entry.deployment_id,
                current_status=previous_status,
                target_status=target,
                reason=entry.reason,
                step_failure=type(exc).__name__,
            ) from exc

        deployment.status = target
        updated = await self.deployment_repository.save(deployment)

        self._emit_operation_log(
            deployment_id=entry.deployment_id,
            previous_status=previous_status,
            current_status=target,
            reason=entry.reason,
        )

        return PromotionResult(
            deployment_id=entry.deployment_id,
            successful=True,
            previous_status=previous_status,
            current_status=updated.status,
            reason=entry.reason,
            steps=steps,
        )

    # ------------------------------------------------------------------
    # Adapter call sequence
    # ------------------------------------------------------------------

    async def _resolve_artifact(self, deployment: Deployment) -> Any:
        result = self.artifact.resolve(ref=deployment.artifact_ref)
        self.artifact.validate(
            ref=deployment.artifact_ref,
            expected_version=deployment.artifact_ref,
        )
        return result

    async def _place(
        self,
        deployment: Deployment,
        entry: PromotionEntry,
    ) -> Any:
        return self.placement.place(
            deployment_id=deployment.id,
            run_id=deployment.id,
            artifact_ref=deployment.artifact_ref,
            target_environment=None,
            resource_profile=None,
            routing_hints=None,
        )

    def _expose(self, deployment: Deployment, target: str) -> Any:
        # Real exposure slices are handled by ExposureController.
        # Here we just record the first exposure step required by promotion.
        if target in {"active", "promoted"}:
            return self.exposure.begin_limited(
                deployment_id=deployment.id,
                route_id=None,
                slice_params=None,
            )
        return {}

    def _update_registry(
        self,
        deployment: Deployment,
        target: str,
        entry: PromotionEntry,
    ) -> Any:
        # Registry promotion is the serving-path registration side.
        return self.registry.promote(
            serving_path_id=deployment.id,
            new_serving=deployment.artifact_ref,
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
    ) -> None:
        # Operation logging is a future slice. This stub exists so the
        # orchestrator shape is stable even before that repository is real.
        _operation_log_entry = {
            "deployment_id": deployment_id,
            "previous_status": previous_status,
            "current_status": current_status,
            "reason": reason,
        }
        return
