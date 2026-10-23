"""Rollback API handlers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from deployctl.api.dependencies import ApiRouterDependencies


class RollbackRouter:
    """Rollback-related API routes."""

    def __init__(self, *, dependencies: ApiRouterDependencies) -> None:
        self.dependencies = dependencies

    def __getitem__(self, name: str) -> Any:
        value = getattr(self, name, None)
        if value is None:
            raise KeyError(f"no dependency named {name!r}")
        return value

    def route(self) -> APIRouter:
        router = APIRouter(prefix="/rollbacks")

        @router.post("/{deployment_id}/rollback", status_code=200)
        def rollback(deployment_id: str, body: dict) -> JSONResponse:
            raise HTTPException(status_code=501, detail="not implemented")

        return router
