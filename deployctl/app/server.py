"""FastAPI application factory for deployctl."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from deployctl.api import router as api_router
from deployctl.app.config import Config
from deployctl.app.dependencies import build_dependencies


def create_app(*, config: Config | None = None) -> FastAPI:
    """Create the FastAPI application.

    Building the app is synchronous and touches no I/O, so the factory is safe
    to call from inside a running event loop, as
    ``uvicorn --factory deployctl.app.server:create_app`` does. The database
    schema is created in the lifespan when the server starts.
    """
    deps = build_dependencies(config=config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await deps.create_schema()
        try:
            yield
        finally:
            await deps.dispose()

    app = FastAPI(title="deployctl", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router.build_router(dependencies=deps))

    return app


def expose_routes(*, config: Config | None = None) -> list[tuple[str, set[str]]]:
    """Return the mounted route paths and methods for inspection.

    This exists purely so tests and scripts can assert the API surface
    without starting a server.
    """
    app = create_app(config=config)
    paths: list[tuple[str, set[str]]] = []

    def walk(routes, prefix: str = ""):
        for route in routes:
            if isinstance(route, Mount):
                walk(route.app.routes, prefix=prefix + (route.path or ""))
            elif isinstance(route, Route):
                paths.append((prefix + (route.path or ""), route.methods))

    from starlette.routing import Mount, Route

    walk(app.routes)
    return paths
