"""DB-backed tests for the first persistence milestone.

These tests exercise the real async SQLAlchemy `DeploymentRepository`
backing the deployment slice, plus the system health endpoint, so we can
confirm the control plane is stateful end to end.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from deployctl.app import dependencies as dependencies_module
from deployctl.app.config import Config
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

    These tests interleave explicit ``asyncio.run()`` blocks with the
    synchronous service, which starts its own loop per call. ``NullPool`` keeps
    every connection inside the loop that opened it: SQLite happens to tolerate
    a pooled connection being reused across loops, ``asyncpg`` raises "Event
    loop is closed".
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


def test_app_engine_keeps_connections_out_of_the_pool(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A request must not leave a connection for the next request's event loop.

    The deployment routes are synchronous handlers that call ``asyncio.run`` per
    request, so each request runs on a fresh loop. A pooled engine would park
    request 1's connection in the pool and hand it to request 2, which asyncpg
    rejects with "Event loop is closed"; SQLite tolerates exactly that, so the
    Postgres lane was the only thing that noticed when the pool came back.

    This asserts the property the fix relies on, locally and on every dialect:
    the app's engine never holds a connection between requests.
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
                "description": "loop-owned connection",
                "artifact_ref": "artifact://example/loop-owned@v1",
            },
        )
        assert created.status_code == 201, created.text

        # Nothing is kept for a later request: the engine hands every loop its
        # own connection and closes it on release.
        assert isinstance(engine.pool, NullPool), (
            "the app engine must not pool connections: each sync request runs "
            "on its own event loop, and asyncpg rejects a connection opened on "
            "a closed one (see build_dependencies)"
        )


def test_deployment_create_and_get_via_service(client_full):
    _, _, service = client_full

    payload = {
        "description": "Service-backed deployment",
        "artifact_ref": "artifact://example/service@v1",
    }

    created = service.create_deployment(payload)
    assert created["status"] == "planned"

    retrieved = service.get_deployment(created["deployment_id"])
    assert retrieved["deployment_id"] == created["deployment_id"]
    assert retrieved["description"] == payload["description"]
    assert retrieved["artifact_ref"] == payload["artifact_ref"]
    assert retrieved["status"] == "planned"
    assert retrieved["created_at"] == created["created_at"]
