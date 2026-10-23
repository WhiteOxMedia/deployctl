"""System API handlers."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from deployctl.api.dependencies import ApiRouterDependencies


class SystemRouter:
    """System-level API routes."""

    def __init__(self, *, dependencies: ApiRouterDependencies) -> None:
        self.dependencies = dependencies

    def route(self) -> APIRouter:
        router = APIRouter(prefix="/system")

        @router.get("/health")
        def health() -> JSONResponse:
            return JSONResponse(
                content={
                    "ok": True,
                    "service": "deployctl",
                    "version": "0.1.0",
                }
            )

        return router
