"""Exposure orchestration controller for the deployment control plane.

This controller handles exposure shifts for a deployment. Right now it is
intentionally thin:

- load a deployment from the repository
- ask the exposure adapter to shift exposure
- write the updated deployment back
- emit a stub operation-log entry
- return an ExposureResult DTO

It does not implement promotion or rollback. Those belong in
PromotionEngine and RollbackCoordinator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deployctl.adapters.exposure import ExposureAdapter
from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.errors import (
    DeploymentNotFoundError,
    ExposureError,
    ExposureNotReadyError,
)
from deployctl.domain.readiness import ReadinessRecord, ReadinessStatus
from deployctl.persistence.repository import DeploymentRepository
from deployctl.service.orchestration.readiness_controller import ReadinessController


@dataclass(frozen=True)
class ExposureRequest:
    """One requested exposure shift."""

    deployment_id: str
    action: str
    route_id: str | None = None
    slice_params: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExposureResult:
    """Outcome of an exposure attempt."""

    deployment_id: str
    action: str
    successful: bool
    current_status: str
    error: str | None = None
    adapter_output: dict[str, Any] | None = None
    readiness: ReadinessRecord | None = None
    readiness_status: str | None = None


def _build_exposure_error(
    deployment_id: str,
    action: str,
    reason: str,
) -> Exception:
    """Build the exposure failure exception used by this controller.

    This helper is the single place that knows how to construct an
    `ExposureError` from the controller's preferred arguments. If the
    real `ExposureError` constructor changes, fix this helper here.
    """
    return ExposureError(
        message=(
            f"Exposure shift {action} failed for deployment {deployment_id}: {reason}"
        ),
        code="exposure_shift_failed",
        details={
            "deployment_id": deployment_id,
            "action": action,
            "reason": reason,
        },
    )


class ExposureController:
    """Orchestrates exposure shifts for deployments.

    Public surface is deliberately small so it can be tested against a
    real DeploymentRepository without requiring the rest of the vertical
    slices to be wired yet.

    Exposure changes are gated on readiness: they require a healthy readiness
    record before the controller will shift exposure. If readiness has not been
    evaluated yet, the controller still allows the change because there is no
    evidence that the deployment is unhealthy.
    """

    def __init__(
        self,
        *,
        deployment_repository: DeploymentRepository,
        exposure: ExposureAdapter,
        readiness_controller: ReadinessController | None = None,
    ) -> None:
        self.deployment_repository = deployment_repository
        self.exposure = exposure
        self.readiness_controller = readiness_controller

    async def shift(self, request: ExposureRequest) -> ExposureResult:
        """Run one exposure shift attempt.

        Raises:
            DeploymentNotFoundError: if the deployment does not exist.
        """
        deployment = await self.deployment_repository.get_by_id(request.deployment_id)
        if deployment is None:
            raise DeploymentNotFoundError(
                message=f"deployment not found: {request.deployment_id}",
                details={"deployment_id": request.deployment_id},
            )

        previous_status = deployment.status
        adapter_output: dict[str, Any] = {}

        # Gate exposure changes on readiness. Exposure should not shift while a
        # deployment is known to be unhealthy, but it may still shift when readiness
        # has not been evaluated yet.
        readiness = await self._check_readiness(request.deployment_id)
        if readiness is not None and readiness.status is not ReadinessStatus.ready:
            raise ExposureNotReadyError(
                message=(
                    f"exposure shift blocked: deployment {request.deployment_id!r} "
                    f"is not ready"
                ),
                code="exposure_not_ready",
                details={
                    "deployment_id": request.deployment_id,
                    "readiness_status": readiness.status.value,
                    "readiness_observed_at": readiness.observed_at.isoformat(),
                },
            )

        try:
            adapter_output = self._call_exposure(request, deployment)
        except Exception as exc:
            raise _build_exposure_error(
                deployment_id=request.deployment_id,
                action=request.action,
                reason=f"{type(exc).__name__}: {exc}",
            ) from exc

        updated = await self.deployment_repository.save(deployment)
        self._emit_operation_log(
            deployment_id=request.deployment_id,
            action=request.action,
            previous_status=previous_status,
            current_status=updated.status,
        )

        return ExposureResult(
            deployment_id=request.deployment_id,
            action=request.action,
            successful=True,
            current_status=updated.status,
            adapter_output=adapter_output,
            readiness=readiness,
            readiness_status=readiness.status.value if readiness is not None else None,
        )

    def _call_exposure(
        self, request: ExposureRequest, deployment: Deployment
    ) -> dict[str, Any]:
        if request.action == "begin_limited":
            call = self.exposure.begin_limited(
                deployment_id=deployment.id,
                route_id=request.route_id,
                slice_params=request.slice_params,
            )
        elif request.action == "increase_slice":
            call = self.exposure.increase_slice(
                deployment_id=deployment.id,
                route_id=request.route_id,
                slice_params=request.slice_params,
            )
        elif request.action == "full_exposure":
            call = self.exposure.full_exposure(
                deployment_id=deployment.id,
                route_id=request.route_id,
                slice_params=request.slice_params,
            )
        elif request.action == "retract":
            call = self.exposure.retract(
                deployment_id=deployment.id,
                route_id=request.route_id,
                slice_params=request.slice_params,
            )
        elif request.action == "status":
            call = self.exposure.status(
                deployment_id=deployment.id,
                route_id=request.route_id,
            )
        else:
            raise _build_exposure_error(
                deployment_id=request.deployment_id,
                action=request.action,
                reason="not implemented",
            )

        return dict(call) if isinstance(call, dict) else {}

    async def _check_readiness(self, deployment_id: str) -> ReadinessRecord | None:
        """Return the latest readiness record if readiness is wired in.

        Returns ``None`` when readiness is not wired so older callers keep working
        while readiness is rolled out piece by piece.
        """

        controller = self.readiness_controller
        if controller is None:
            return None
        return await controller.get_status(deployment_id=deployment_id)

    def _emit_operation_log(
        self,
        *,
        deployment_id: str,
        action: str,
        previous_status: str,
        current_status: str,
    ) -> None:
        # Operation logging is a future slice. This stub exists so the
        # controller shape is stable even before that repository is real.
        _operation_log_entry = {
            "deployment_id": deployment_id,
            "action": action,
            "previous_status": previous_status,
            "current_status": current_status,
        }
        return
