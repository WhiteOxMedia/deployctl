"""FastAPI application factory for deployctl."""

from __future__ import annotations

import queue
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from alembic import command
from alembic import config as alembic_cfg
from fastapi import FastAPI
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from deployctl.api import router as api_router
from deployctl.app.config import Config
from deployctl.app.dependencies import build_dependencies


def create_app(*, config: Config | None = None) -> FastAPI:
    """Create the FastAPI application.

    Building the app is synchronous and touches no I/O, so the factory is safe
    to call from inside a running event loop, as
    ``uvicorn --factory deployctl.app.server:create_app`` does.

    By default the startup lifespan applies the Alembic migration chain
    (``alembic upgrade head``) before the first request, bringing a fresh
    database to head and leaving an already-migrated one untouched. Set
    ``Config.apply_migrations_on_startup`` to ``False`` to require the schema to
    exist beforehand; the test suite does that because its fixture has already
    migrated the throwaway database.
    """
    deps = build_dependencies(config=config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            if deps.config.apply_migrations_on_startup:
                _apply_migrations(config=deps.config)
            yield
        finally:
            await deps.dispose()

    app = FastAPI(title="deployctl", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router.build_router(dependencies=deps))

    return app


def _apply_migrations(*, config: Config) -> None:
    """Apply Alembic migrations to whichever database the app was configured with.

    This uses the same :class:`Config` path as the application itself, so it is
    wired to the same URL that startup has already opened. ``alembic.ini`` only
    keeps a small placeholder so the Alembic module can import cleanly; the real
    database URL is injected at runtime from ``Config.engine_url()`` instead of
    being edited here.

    This path is intentionally kept generic so deploy scripts can reuse the same
    override problem without hardcoding a production driver inside the server.

    Failures are re-raised as a :class:`RuntimeError` that names the target
    database (with any password redacted) so startup logs say which database
    could not be migrated instead of surfacing a bare driver error.
    """

    def _target() -> None:
        cfg = alembic_cfg.Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", config.engine_url())
        # Keep the server's logging configuration. migrations/env.py's
        # ``fileConfig`` would replace handlers and, worse, disable the uvicorn
        # loggers that report a startup failure.
        cfg.attributes["configure_logging"] = False
        command.upgrade(cfg, "head")

    results: queue.Queue[BaseException | None] = queue.Queue()

    def _run() -> None:
        try:
            _target()
            results.put(None)
        except BaseException as exc:
            results.put(exc)

    t = threading.Thread(target=_run, name="alembic")
    t.start()
    t.join()
    err = results.get()
    if err is None:
        return
    if not isinstance(err, Exception):
        # Cancellation-style exits (KeyboardInterrupt and friends) keep their type.
        raise err
    raise RuntimeError(
        "failed to apply Alembic migrations to "
        f"{describe_database_url(config.engine_url())}: {err}"
    ) from err


def describe_database_url(database_url: str) -> str:
    """Render a database URL for diagnostics, hiding any password.

    URLs without a password are returned verbatim so local paths stay readable;
    only credentials are rewritten through SQLAlchemy's redacting renderer.
    """
    try:
        url = make_url(database_url)
    except ArgumentError:
        return database_url
    if url.password is None:
        return database_url
    return url.render_as_string(hide_password=True)


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
