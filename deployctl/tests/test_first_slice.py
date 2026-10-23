"""First vertical slice tests for the deployment flow."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import NullPool

from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.errors import (
    DeploymentDuplicateError,
    DeploymentNotFoundError,
)
from deployctl.persistence.engine import create_async_engine, create_session_factory
from deployctl.persistence.repository import SqlAlchemyDeploymentRepository
from deployctl.service.deployments.deployment_service import DeploymentService


@pytest.fixture
def client(app_client: TestClient) -> Iterator[TestClient]:
    """The shared app client, backed by the migration-created database."""
    yield app_client


def _loop_owned_engine(database_url: str):
    """An engine whose connections never outlive the loop that opened them.

    These tests interleave explicit ``asyncio.run()`` blocks with the
    synchronous ``DeploymentService``, which starts its own loop per call. A
    pooled engine would hand a connection opened on one loop to the next, which
    SQLite happens to tolerate and a server dialect (asyncpg) rejects.
    """
    return create_async_engine(database_url, poolclass=NullPool)


def test_deployment_create_and_get(client: TestClient) -> None:
    payload = {
        "description": "Deploy candidate v1",
        "artifact_ref": "artifact://example/app@v1",
    }

    create_resp = client.post("/api/v1/deployments/", json=payload)
    assert create_resp.status_code == 201, create_resp.json()
    created = create_resp.json()
    deployment_id = created["deployment_id"]

    assert created["description"] == payload["description"]
    assert created["artifact_ref"] == payload["artifact_ref"]
    assert created["status"] == "planned"
    assert "created_at" in created

    get_resp = client.get(f"/api/v1/deployments/{deployment_id}")
    assert get_resp.status_code == 200, get_resp.json()
    assert get_resp.json()["deployment_id"] == deployment_id


def test_deployment_create_requires_description(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/deployments/",
        json={"artifact_ref": "artifact://x"},
    )
    assert resp.status_code == 422, resp.json()


def test_deployment_create_duplicate_rejected(migrated_database_url: str) -> None:
    engine = _loop_owned_engine(migrated_database_url)
    factory = create_session_factory(engine)
    repo = SqlAlchemyDeploymentRepository(session_factory=factory)
    service = DeploymentService(deployment_repository=repo)

    async def _seed() -> None:
        await repo.save(
            Deployment(
                id="dup-1",
                description="dup",
                artifact_ref="artifact://x",
                status="planned",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                metadata={},
            )
        )

    try:
        asyncio.run(_seed())
        # The service owns its own event loop, so it is called synchronously.
        with pytest.raises(DeploymentDuplicateError):
            service.create_deployment(
                {
                    "deployment_id": "dup-1",
                    "description": "dup",
                    "artifact_ref": "artifact://x",
                }
            )
    finally:
        asyncio.run(engine.dispose())


def test_deployment_get_unknown(migrated_database_url: str) -> None:
    engine = _loop_owned_engine(migrated_database_url)
    factory = create_session_factory(engine)
    repo = SqlAlchemyDeploymentRepository(session_factory=factory)
    service = DeploymentService(deployment_repository=repo)

    try:
        with pytest.raises(DeploymentNotFoundError):
            service.get_deployment("missing")
    finally:
        asyncio.run(engine.dispose())


def test_system_health(client: TestClient) -> None:
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["ok"] is True
    assert body["service"] == "deployctl"
