"""DB-backed tests for the first persistence milestone.

These tests exercise the real async SQLAlchemy `DeploymentRepository`
backing the deployment slice, plus the system health endpoint, so we can
confirm the control plane is stateful end to end.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from deployctl.app import dependencies as dependencies_module
from deployctl.app.config import Config
from deployctl.app.dependencies import build_dependencies
from deployctl.app.server import create_app
from deployctl.persistence.engine import create_async_engine, create_session_factory
from deployctl.persistence.repository import SqlAlchemyDeploymentRepository
from deployctl.service.deployments.deployment_service import DeploymentService


def async_run(callback):
    """Run an async callable in the current thread's event loop."""
    return asyncio.run(callback())


@pytest.fixture
def engine(config):
    """An engine for the migrated test database.

    ``config`` comes from ``conftest`` and disables startup migrations, so the
    Alembic chain is applied exactly once per test by the shared fixture.

    These tests drive the repository from several separate ``asyncio.run()``
    blocks, so ``NullPool`` keeps every connection inside the loop that opened
    it: SQLite happens to tolerate a pooled connection being reused across
    loops, ``asyncpg`` raises "Event loop is closed". The application's own
    engine is unaffected because its handlers share one loop.
    """
    engine = create_async_engine(config.engine_url(), poolclass=NullPool)
    yield engine
    async_run(engine.dispose)


@pytest.fixture
def client_full(app_client: TestClient, engine) -> Iterator[tuple]:
    session_factory = create_session_factory(engine)
    repo = SqlAlchemyDeploymentRepository(session_factory=session_factory)
    service = DeploymentService(deployment_repository=repo)
    yield app_client, repo, service


def test_system_health_still_works(client_full):
    test_client, *_ = client_full
    resp = test_client.get("/api/v1/system/health")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["ok"] is True
    assert body["service"] == "deployctl"


def test_deployment_persists_across_sessions(client_full):
    test_client, repo, _service = client_full

    payload = {
        "description": "Persisted deployment",
        "artifact_ref": "artifact://example/persisted@v1",
    }

    create_resp = test_client.post("/api/v1/deployments/", json=payload)
    assert create_resp.status_code == 201, create_resp.json()
    created = create_resp.json()
    deployment_id = created["deployment_id"]

    found = async_run(lambda: repo.get_by_id(deployment_id))
    assert found is not None
    assert found.description == payload["description"]
    assert found.artifact_ref == payload["artifact_ref"]
    assert found.status == "planned"

    found_again = async_run(lambda: repo.get_by_id(deployment_id))
    assert found_again is not None
    assert found_again.id == deployment_id
    assert found_again.description == found.description
    assert found_again.artifact_ref == found.artifact_ref
    assert found_again.status == found.status

    get_resp = test_client.get(f"/api/v1/deployments/{deployment_id}")
    assert get_resp.status_code == 200, get_resp.json()
    body = get_resp.json()
    assert body["deployment_id"] == deployment_id
    assert body["description"] == payload["description"]
    assert body["artifact_ref"] == payload["artifact_ref"]
    assert body["status"] == "planned"


def test_deployment_duplicate_rejected_db(client_full):
    test_client, repo, _service = client_full

    payload = {
        "deployment_id": "dup-db-1",
        "description": "dup",
        "artifact_ref": "artifact://x",
    }

    first_create = test_client.post("/api/v1/deployments/", json=payload)
    assert first_create.status_code == 201, first_create.json()
    first_id = first_create.json()["deployment_id"]

    second_create = test_client.post("/api/v1/deployments/", json=payload)
    assert second_create.status_code == 409, second_create.json()
    assert second_create.json()["detail"].startswith("deployment already exists")

    found = async_run(lambda: repo.get_by_id(first_id))
    assert found is not None
    assert found.id == first_id
    assert found.description == payload["description"]
    assert found.artifact_ref == payload["artifact_ref"]
    assert found.status == "planned"


def test_app_engine_pools_connections_across_requests(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requests share the app's event loop, so the engine pools connections.

    This replaces the earlier per-request ``NullPool`` guard. Now that the
    deployment routes are ``async def``, a connection opened for one request
    belongs to the same loop as the next request and can be reused, so pooling
    is the point again; the assertions fail if the engine goes back to
    ``NullPool``, the workaround this change removes.

    The other half of that pairing cannot be asserted here — a handler that
    starts its own loop still works on SQLite — but it is enforced twice over:
    ``await`` inside a ``def`` is a syntax error, and the two DB-backed requests
    below are the same pair the Postgres lane runs against ``postgres:17``,
    where asyncpg rejects a connection from a closed loop.
    """
    engines: list[AsyncEngine] = []
    real_create_async_engine = dependencies_module.create_async_engine

    def _capturing_create_async_engine(*args: Any, **kwargs: Any) -> AsyncEngine:
        engine = real_create_async_engine(*args, **kwargs)
        engines.append(engine)
        return engine

    monkeypatch.setattr(
        dependencies_module, "create_async_engine", _capturing_create_async_engine
    )

    app = create_app(config=config)
    assert len(engines) == 1, "create_app should build exactly one engine"
    engine = engines[0]

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/deployments/",
            json={
                "description": "pooled connection",
                "artifact_ref": "artifact://example/pooled@v1",
            },
        )
        assert created.status_code == 201, created.text

        # The connection came back to the pool for the next request instead of
        # being opened and thrown away per request.
        assert not isinstance(engine.pool, NullPool)
        assert engine.pool.checkedin() >= 1

        deployment_id = created.json()["deployment_id"]
        fetched = client.get(f"/api/v1/deployments/{deployment_id}")
        assert fetched.status_code == 200, fetched.text


def test_app_engine_takes_pool_settings_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pool is sized from ``Config``, not from SQLAlchemy's defaults."""
    captured: dict[str, Any] = {}
    real_create_async_engine = dependencies_module.create_async_engine

    def _capturing_create_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return real_create_async_engine(url, **kwargs)

    monkeypatch.setattr(
        dependencies_module, "create_async_engine", _capturing_create_async_engine
    )

    config = Config(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'pool.db'}",
        pool_size=3,
        max_overflow=7,
        pool_recycle=120,
    )
    deps = build_dependencies(config=config)
    try:
        assert captured["kwargs"] == {
            "pool_size": 3,
            "max_overflow": 7,
            "pool_recycle": 120,
        }
        # The pool really was built with the configured size, not just passed.
        assert deps.engine.pool.size() == 3
    finally:
        asyncio.run(deps.dispose())


def test_in_memory_sqlite_keeps_its_dialect_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An in-memory database has no pool to size, and must still build.

    SQLite in-memory is served by ``StaticPool``: one connection holding the one
    database. That pool rejects ``pool_size``/``max_overflow``, so the engine is
    created without the config settings instead of failing to start.
    """
    captured: dict[str, Any] = {}
    real_create_async_engine = dependencies_module.create_async_engine

    def _capturing_create_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return real_create_async_engine(url, **kwargs)

    monkeypatch.setattr(
        dependencies_module, "create_async_engine", _capturing_create_async_engine
    )

    deps = build_dependencies(
        config=Config(database_url="sqlite+aiosqlite:///:memory:", pool_size=3)
    )
    try:
        assert captured["kwargs"] == {}
        assert type(deps.engine.pool).__name__ == "StaticPool"
    finally:
        asyncio.run(deps.dispose())


def test_deployment_create_and_get_via_service(client_full):
    _, _, service = client_full

    payload = {
        "description": "Service-backed deployment",
        "artifact_ref": "artifact://example/service@v1",
    }

    async def _run() -> tuple[dict, dict]:
        created = await service.create_deployment(payload)
        retrieved = await service.get_deployment(created["deployment_id"])
        return created, retrieved

    created, retrieved = async_run(_run)
    assert created["status"] == "planned"
    assert retrieved["deployment_id"] == created["deployment_id"]
    assert retrieved["description"] == payload["description"]
    assert retrieved["artifact_ref"] == payload["artifact_ref"]
    assert retrieved["status"] == "planned"
    assert retrieved["created_at"] == created["created_at"]
