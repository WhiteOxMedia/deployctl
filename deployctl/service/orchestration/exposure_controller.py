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
from deployctl.domain.errors import DeploymentNotFoundError, ExposureError
from deployctl.persistence.repository import DeploymentRepository


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
    """

    def __init__(
        self,
        *,
        deployment_repository: DeploymentRepository,
        exposure: ExposureAdapter,
    ) -> None:
        self.deployment_repository = deployment_repository
        self.exposure = exposure

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
