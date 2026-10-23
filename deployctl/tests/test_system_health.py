"""System health endpoint tests.

``/health`` stays a dependency-free liveness check. ``/api/v1/system/health``
checks a connection out of the engine pool and runs ``SELECT 1``, so a dead pool
shows up as 503 on the probe instead of as a failed deployment request.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

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
