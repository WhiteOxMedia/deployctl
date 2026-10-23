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
        async def health() -> JSONResponse:
            """Report service health, including whether the database answers.

            The probe checks a connection out of the engine pool and runs
            ``SELECT 1``, so a pool that cannot serve a connection shows up here
            as a 503 instead of as the next deployment request failing. An
            empty but reachable database is healthy: this checks connectivity,
            not the schema.
            """
            content = {
                "ok": True,
                "service": "deployctl",
                "version": "0.1.0",
                "database": "up",
            }
            try:
                await self.dependencies.check_database()
            except Exception as exc:
                # The driver's message can embed the database URL, credentials
                # included, so the response names the failure type only.
                return JSONResponse(
                    status_code=503,
                    content={
                        **content,
                        "ok": False,
                        "database": "down",
                        "error": type(exc).__name__,
                    },
                )
            return JSONResponse(content=content)

        return router
