"""Readiness API handlers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from deployctl.api.dependencies import ApiRouterDependencies
from deployctl.api.schemas.readiness import (
    ProbeRequest,
    ProbeResponse,
    ReadinessResponse,
)
from deployctl.domain.readiness import ReadinessStatus
from deployctl.service.orchestration.readiness_controller import ReadinessController


class ReadinessRouter:
    """Readiness-related API routes."""

    def __init__(self, *, dependencies: ApiRouterDependencies) -> None:
        self.dependencies = dependencies

    def __getitem__(self, name: str) -> Any:
        value = getattr(self, name, None)
        if value is None:
            raise KeyError(f"no dependency named {name!r}")
        return value

    def _controller(self) -> ReadinessController:
        """Resolve the controller at request time so route building needs no wiring."""
        return ReadinessController(
            readiness_repository=self.dependencies["readiness_repository"],
            probe_adapter=self.dependencies["probe_adapter"],
        )

    def route(self) -> APIRouter:
        router = APIRouter(prefix="/deployments")

        @router.get(
            "/{deployment_id}/readiness",
            response_model=ReadinessResponse,
            status_code=200,
        )
        async def get_readiness(deployment_id: str) -> ReadinessResponse:
            record = await self._controller().get_status(deployment_id=deployment_id)
            if record is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"no readiness record found for deployment {deployment_id}"
                    ),
                )
            assert record is not None  # for mypy; we already raised 404 above
            return ReadinessResponse(
                deployment_id=record.deployment_id,
                status=record.status.value,
                details=record.details,
                observed_at=record.observed_at,
                scope_id=record.scope_id,
                source_id=record.source_id,
            )

        @router.post(
            "/{deployment_id}/probe",
            response_model=ProbeResponse,
            status_code=201,
        )
        async def probe_readiness(
            deployment_id: str,
            body: ProbeRequest | None = None,
        ) -> ProbeResponse:
            record = await self._controller().evaluate(
                deployment_id=deployment_id,
                scope_id=body.scope_id if body else None,
                source_id=body.source_id if body else None,
                params=body.params if body else None,
            )
            return ProbeResponse(
                deployment_id=record.deployment_id,
                status=record.status.value,
                healthy=record.status == ReadinessStatus.ready,
                details=record.details,
                observed_at=record.observed_at,
                scope_id=record.scope_id,
                source_id=record.source_id,
            )

        return router
