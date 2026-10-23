"""FastAPI application factory for deployctl."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from deployctl.api import router as api_router
from deployctl.app.config import Config
from deployctl.app.dependencies import (
    ApplicationDependencies,
    build_dependencies,
)
from deployctl.app.null_adapters import NullPromotionAdapter
from deployctl.persistence.base import Base
from deployctl.persistence.readiness_repository import SqlAlchemyReadinessRepository
from deployctl.persistence.repository import SqlAlchemyDeploymentRepository
from deployctl.service.deployments import deployment_service
from deployctl.service.orchestration.exposure_controller import ExposureController
from deployctl.service.orchestration.promotion import PromotionEngine
from deployctl.service.orchestration.readiness_controller import ReadinessController
from deployctl.service.orchestration.rollback_coordinator import RollbackCoordinator


def create_app(*, config: Config | None = None) -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="deployctl", version="0.1.0")

    deps = build_dependencies(config=config)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router.build_router(dependencies=deps))

    return app


async def _build_app_async(*, config: Config | None = None) -> FastAPI:
    """Async application factory for process managers that already hold a loop."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    if config is None:
        config = Config()

    deps = ApplicationDependencies(config=config)

    engine = create_async_engine(config.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    deps.deployment_repository = SqlAlchemyDeploymentRepository(
        session_factory=factory,
    )
    deps.deployment_service = deployment_service.DeploymentService(
        deployment_repository=deps.deployment_repository,
    )
    deps.exposure_controller = ExposureController(
        deployment_repository=deps.deployment_repository,
        exposure=deps._null_exposure_adapter,
    )
    deps.rollback_coordinator = RollbackCoordinator(
        deployment_repository=deps.deployment_repository,
        registry=deps._null_registry_adapter,
    )
    deps.promotion_engine = PromotionEngine(
        deployment_repository=deps.deployment_repository,
        promotion=NullPromotionAdapter(),
        registry=deps._null_registry_adapter,
    )

    repo = SqlAlchemyReadinessRepository(session_factory=factory)
    deps.readiness_repository = repo
    deps.readiness_controller = ReadinessController(
        readiness_repository=repo,
        probe_adapter=deps._null_probe_adapter,
    )

    app = FastAPI(title="deployctl", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router.build_router(dependencies=deps))

    return app


def create_app_async(*, config: Config | None = None) -> FastAPI:
    """Build the app from inside an async context without nesting asyncio.run()."""
    import asyncio

    return asyncio.run(_build_app_async(config=config))


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


def run_dev(*, config: Config | None = None) -> FastAPI:
    """Create the application for local development and testing."""
    return create_app(config=config)
