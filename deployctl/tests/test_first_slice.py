"""First vertical slice tests for the deployment flow."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from deployctl.app.config import Config
from deployctl.app.server import create_app
from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.errors import (
    DeploymentDuplicateError,
    DeploymentNotFoundError,
)
from deployctl.persistence.base import Base
from deployctl.persistence.engine import (
    create_async_engine,
    create_session_factory,
)
from deployctl.persistence.repository import SqlAlchemyDeploymentRepository
from deployctl.service.deployments.deployment_service import DeploymentService


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_deployment_create_and_get(client: TestClient):

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


def test_deployment_create_requires_description(client: TestClient):

    resp = client.post(
        "/api/v1/deployments/",
        json={"artifact_ref": "artifact://x"},
    )
    assert resp.status_code == 422, resp.json()


def test_deployment_create_duplicate_rejected():
    engine = create_async_engine(
        Config().database_url.replace("deployctl.db", f"dup-test-{uuid.uuid4().hex}.db")
    )
    factory = create_session_factory(engine)

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())

    repo = SqlAlchemyDeploymentRepository(session_factory=factory)

    async def _seed():
        saved = await repo.save(
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
        assert saved is not None
        assert saved.id == "dup-1"

    asyncio.run(_seed())

    service = DeploymentService(deployment_repository=repo)

    with pytest.raises(DeploymentDuplicateError):
        service.create_deployment(
            {
                "deployment_id": "dup-1",
                "description": "dup",
                "artifact_ref": "artifact://x",
            }
        )

    asyncio.run(engine.dispose())


def test_deployment_get_unknown():
    engine = create_async_engine(Config().database_url)
    factory = create_session_factory(engine)

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())

    repo = SqlAlchemyDeploymentRepository(session_factory=factory)
    service = DeploymentService(deployment_repository=repo)

    with pytest.raises(DeploymentNotFoundError):
        service.get_deployment("missing")

    asyncio.run(engine.dispose())


def test_system_health(client: TestClient):

    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["ok"] is True
    assert body["service"] == "deployctl"
