"""DB-backed tests for the first persistence milestone.

These tests exercise the real async SQLAlchemy `DeploymentRepository`
backing the deployment slice, plus the system health endpoint, so we can
confirm the control plane is stateful end to end.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from deployctl.persistence.engine import create_engine
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
    """
    return create_engine(config)


@pytest.fixture
def client_full(app_client: TestClient, engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repo = SqlAlchemyDeploymentRepository(session_factory=session_factory)
    service = DeploymentService(deployment_repository=repo)
    yield app_client, repo, service
    async_run(engine.dispose)


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
