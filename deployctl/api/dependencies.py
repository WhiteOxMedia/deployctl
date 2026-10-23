"""API dependency wiring for the API layer.

This module lives alongside the API handlers and re-exposes the
application dependency container so the handlers stay decoupled from
the concrete ``ApplicationDependencies`` shape used in
``deployctl.app.dependencies``.
"""

from __future__ import annotations

from typing import Any

try:
    from deployctl.app.dependencies import ApplicationDependencies as _AppDeps
except Exception:  # pragma: no cover - import guard for tests
    _AppDeps = None  # type: ignore[assignment]

# Keep a local reference so the API layer can type-check against the same
# container shape the rest of the application uses.
ApplicationDependencies = _AppDeps  # type: ignore[misc,assignment]


def api_dependencies_from(deps: ApplicationDependencies) -> ApiRouterDependencies:
    """Build an API-layer dependency bag from an application container.

    This keeps the handlers decoupled from the concrete
    ``ApplicationDependencies`` shape while still giving them access to
    every runtime dependency by name.
    """
    return ApiRouterDependencies(deps=deps)


class ApiRouterDependencies:
    """Explicit API-layer dependency bag.

    This is the object the API handlers accept so the routing layer can
    be tested without importing ``deployctl.app.dependencies``.
    """

    def __init__(self, *, deps: ApplicationDependencies | None = None) -> None:
        self.deps = deps

    def __getitem__(self, name: str) -> Any:
        if self.deps is None:
            raise KeyError(f"no API dependency named {name!r}")
        return self.deps[name]

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if self.deps is None:
            raise KeyError(f"no API dependency named {name!r}")
        return getattr(self.deps, name)

    @property
    def deployment_service(self):
        """Direct accessor for the deployment service used by the handlers."""
        if self.deps is None:
            raise KeyError("no API dependency named 'deployment_service'")
        return self.deps.deployment_service

    @property
    def readiness_repository(self):
        """Direct accessor for the readiness repository used by readiness handlers."""
        if self.deps is None:
            raise KeyError("no API dependency named 'readiness_repository'")
        return self.deps.readiness_repository


def get_dependencies() -> ApplicationDependencies:
    """Return the already-built application dependency container.

    Handlers imported through ``ApiRouter`` are expected to resolve
    their dependencies from a pre-built instance that lives on the
    router rather than calling ``build_dependencies`` themselves.
    """
    raise NotImplementedError("placeholder")
