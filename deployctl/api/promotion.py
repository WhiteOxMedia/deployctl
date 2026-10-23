"""Promotion API handlers."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from deployctl.api.dependencies import ApiRouterDependencies


class PromotionRouter:
    """Promotion-related API routes."""

    def __init__(self, *, dependencies: ApiRouterDependencies) -> None:
        self.dependencies = dependencies

    def route(self) -> APIRouter:
        router = APIRouter(prefix="/promotions")

        @router.post("/", status_code=201)
        def promote(body: dict) -> JSONResponse:
            raise HTTPException(status_code=501, detail="not implemented")

        return router
