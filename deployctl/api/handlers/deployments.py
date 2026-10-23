"""Deployment API handlers."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from deployctl.api.dependencies import ApiRouterDependencies
from deployctl.domain.errors import (
    DeploymentDuplicateError,
    DeploymentIntentError,
    DeploymentNotFoundError,
    ExposureError,
    RollbackAnchorError,
    RollbackNotFoundError,
)
from deployctl.service.orchestration.exposure_controller import ExposureRequest
from deployctl.service.orchestration.promotion_engine import PromotionEntry
from deployctl.service.orchestration.rollback_coordinator import RollbackRequest


class DeploymentRouter:
    """Deployment-related API routes."""

    def __init__(self, *, dependencies: ApiRouterDependencies) -> None:
        self.dependencies = dependencies

    def __getitem__(self, name: str) -> Any:
        value = getattr(self, name, None)
        if value is None:
            raise KeyError(f"no dependency named {name!r}")
        return value

    def route(self) -> APIRouter:
        router = APIRouter(prefix="/deployments")

        @router.post("/", status_code=201)
        def create_deployment(body: dict) -> JSONResponse:
            service = self.dependencies.deployment_service
            if service is None:
                raise HTTPException(
                    status_code=501,
                    detail="deployment service not wired",
                )
            try:
                result = service.create_deployment(body)
            except DeploymentIntentError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except DeploymentDuplicateError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return JSONResponse(content=result, status_code=201)

        @router.get("/{deployment_id}")
        def get_deployment(deployment_id: str) -> JSONResponse:
            service = self.dependencies.deployment_service
            if service is None:
                raise HTTPException(
                    status_code=501,
                    detail="deployment service not wired",
                )
            try:
                result = service.get_deployment(deployment_id)
            except DeploymentNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return JSONResponse(content=result)

        @router.post("/{deployment_id}/rollback", status_code=200)
        def rollback_deployment(deployment_id: str, body: dict) -> JSONResponse:
            service = self.dependencies.deployment_service
            coordinator = self.dependencies.rollback_coordinator
            if service is None or coordinator is None:
                raise HTTPException(
                    status_code=501,
                    detail="rollback surface not wired",
                )
            try:
                result = asyncio.run(
                    coordinator.rollback(
                        RollbackRequest(
                            deployment_id=deployment_id,
                            reason=body.get("reason", ""),
                            target_artifact_ref=body.get("target_artifact_ref"),
                        )
                    )
                )
            except DeploymentNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except RollbackNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except RollbackAnchorError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return JSONResponse(content=result)

        @router.post("/{deployment_id}/promote", status_code=200)
        def promote_deployment(deployment_id: str, body: dict) -> JSONResponse:
            service = self.dependencies.deployment_service
            engine = self.dependencies.promotion_engine
            if service is None or engine is None:
                raise HTTPException(
                    status_code=501,
                    detail="promotion surface not wired",
                )
            try:
                result = asyncio.run(
                    engine.promote(
                        PromotionEntry(
                            deployment_id=deployment_id,
                            reason=body.get("reason", ""),
                        )
                    )
                )
            except DeploymentNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return JSONResponse(content=result)

        @router.post("/{deployment_id}/exposure", status_code=200)
        def adjust_exposure(deployment_id: str, body: dict) -> JSONResponse:
            service = self.dependencies.deployment_service
            controller = self.dependencies.exposure_controller
            if service is None or controller is None:
                raise HTTPException(
                    status_code=501,
                    detail="exposure surface not wired",
                )
            try:
                result = asyncio.run(
                    controller.shift(
                        ExposureRequest(
                            deployment_id=deployment_id,
                            action=body.get("action", "status"),
                            slice_params=body.get("slice_params"),
                            route_id=body.get("route_id"),
                        )
                    )
                )
            except DeploymentNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ExposureError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return JSONResponse(
                content={
                    "deployment_id": deployment_id,
                    "action": body.get("action", "status"),
                    "successful": True,
                    "current_status": result.current_status,
                    "adapter_output": result.adapter_output,
                }
            )

        return router
