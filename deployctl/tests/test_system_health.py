"""System health endpoint tests.

``/health`` stays a dependency-free liveness check. ``/api/v1/system/health``
checks a connection out of the engine pool and runs ``SELECT 1``, so a dead pool
shows up as 503 on the probe instead of as a failed deployment request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from deployctl.app import dependencies as dependencies_module
from deployctl.app.config import Config
from deployctl.app.server import create_app


def _unreachable_database_url(tmp_path: Path) -> str:
    """A SQLite URL whose parent directory does not exist.

    Opening it fails the way an unreachable server would, without needing a
    server driver installed.
    """
    return f"sqlite+aiosqlite:///{tmp_path / 'missing-dir' / 'deployctl.db'}"


def test_service_health_reports_database_up(app_client: TestClient) -> None:
    response = app_client.get("/api/v1/system/health")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["service"] == "deployctl"
    assert body["version"] == "0.1.0"
    assert body["database"] == "up"


def test_service_health_does_not_need_the_schema(tmp_path: Path) -> None:
    """The probe checks connectivity, so an empty database is healthy."""
    config = Config(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}",
        apply_migrations_on_startup=False,
    )

    with TestClient(create_app(config=config)) as client:
        response = client.get("/api/v1/system/health")

    assert response.status_code == 200, response.text
    assert response.json()["database"] == "up"


def test_service_health_is_unhealthy_when_the_pool_cannot_connect(
    tmp_path: Path,
) -> None:
    config = Config(
        database_url=_unreachable_database_url(tmp_path),
        apply_migrations_on_startup=False,
    )

    with TestClient(create_app(config=config)) as client:
        response = client.get("/api/v1/system/health")

    assert response.status_code == 503, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["database"] == "down"
    assert body["error"] == "OperationalError"
    # The driver message can carry the DSN; the body carries only its type.
    assert "missing-dir" not in response.text


def test_service_health_reports_503_when_the_pool_loses_its_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A warm pool that can no longer serve a connection must report down.

    The other 503 test starts from a path that never opened, which only proves
    the endpoint can fail. This one proves the failure is caught once the pool
    is live and holding a connection, which is the state an outage leaves it in.

    SQLite connections do not die on their own, so the pool's checkout is made
    to raise the ``OperationalError`` a dropped server connection produces. The
    first probe runs before that listener exists, so the pool genuinely served
    and kept a connection before it went bad.
    """
    config = Config(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'warm.db'}",
        apply_migrations_on_startup=False,
    )

    engines: list[AsyncEngine] = []
    real_create_async_engine = dependencies_module.create_async_engine

    def _capturing_create_async_engine(*args: Any, **kwargs: Any) -> AsyncEngine:
        engine = real_create_async_engine(*args, **kwargs)
        engines.append(engine)
        return engine

    monkeypatch.setattr(
        dependencies_module, "create_async_engine", _capturing_create_async_engine
    )

    with TestClient(create_app(config=config)) as client:
        healthy = client.get("/api/v1/system/health")
        assert healthy.status_code == 200, healthy.text

        assert len(engines) == 1, "create_app should build exactly one engine"
        engine = engines[0]
        assert engine.pool.checkedin() >= 1, (
            "the first probe should have left a live connection in the pool"
        )

        def _dropped_connection(*_args: object) -> None:
            raise OperationalError(
                "SELECT 1",
                {},
                Exception("server closed the connection unexpectedly"),
            )

        event.listen(engine.sync_engine, "checkout", _dropped_connection)

        unhealthy = client.get("/api/v1/system/health")

    assert unhealthy.status_code == 503, unhealthy.text
    body = unhealthy.json()
    assert body["ok"] is False
    assert body["database"] == "down"
    assert body["error"] == "OperationalError"
    # The driver text stays out of the response, on the live-pool path too.
    assert "server closed the connection unexpectedly" not in unhealthy.text


def test_liveness_stays_independent_of_the_database(tmp_path: Path) -> None:
    """Restart probes must not fail just because the database is unreachable."""
    config = Config(
        database_url=_unreachable_database_url(tmp_path),
        apply_migrations_on_startup=False,
    )

    with TestClient(create_app(config=config)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
