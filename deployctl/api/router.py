"""FastAPI router for deployctl."""

from __future__ import annotations

from fastapi import APIRouter

from deployctl.api.dependencies import (
    ApiRouterDependencies,
    ApplicationDependencies,
    api_dependencies_from,
)
from deployctl.api.handlers import (
    deployments,
    exposure,
    origin,
    promotion,
    rollback,
    system,
    version,
)
from deployctl.api.handlers.readiness import ReadinessRouter


def _make_api_dependencies(deps: ApplicationDependencies) -> ApiRouterDependencies:
    """Convert an application dependency container into an API dependency bag."""
    return api_dependencies_from(deps)


class ApiRouter:
    """Top-level API router for the control plane."""

    def __init__(self, *, dependencies: ApplicationDependencies) -> None:
        self.dependencies = dependencies

    def route(self) -> APIRouter:
        api_deps = _make_api_dependencies(self.dependencies)

        system_router = system.SystemRouter(
            dependencies=api_deps,
        ).route()
        deployments_router = deployments.DeploymentRouter(
            dependencies=api_deps,
        ).route()
        promotion_router = promotion.PromotionRouter(
            dependencies=api_deps,
        ).route()
        exposure_router = exposure.ExposureRouter(
            dependencies=api_deps,
        ).route()
        rollback_router = rollback.RollbackRouter(
            dependencies=api_deps,
        ).route()
        origin_router = origin.OriginRouter(
            dependencies=api_deps,
        ).route()
        version_router = version.VersionRouter(
            dependencies=api_deps,
        ).route()
        readiness_router = ReadinessRouter(
            dependencies=api_deps,
        ).route()

        router = APIRouter(prefix="/api/v1")
        router.include_router(system_router)
        router.include_router(deployments_router)
        router.include_router(promotion_router)
        router.include_router(exposure_router)
        router.include_router(rollback_router)
        router.include_router(origin_router)
        router.include_router(version_router)
        router.include_router(readiness_router)
        return router

    def __repr__(self) -> str:
        return f"<ApiRouter dependencies={self.dependencies!r}>"

    @property
    def routes(self) -> list:
        return [self.route()]


def build_router(dependencies: ApplicationDependencies) -> APIRouter:
    """Build and return the top-level APIRouter for ``dependencies``."""
    return ApiRouter(dependencies=dependencies).route()


def build_router_for_app(dependencies: ApplicationDependencies) -> APIRouter:
    """Build the APIRouter tree from ``dependencies`` for the application.

    This helper exists so the FastAPI app factory can construct the
    router without importing the test helpers.
    """
    return build_router(dependencies)
