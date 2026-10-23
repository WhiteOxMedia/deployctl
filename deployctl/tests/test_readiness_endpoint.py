"""End-to-end tests for the readiness API endpoints.

The tests exercise the real HTTP surface (``TestClient``), the readiness
controller, and the SQLAlchemy readiness repository so probe evaluation and
latest-record lookup are verified through the whole stack.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from deployctl.app.config import Config
from deployctl.app.null_adapters import NullProbeAdapter
from deployctl.app.server import create_app
from deployctl.domain.readiness import ReadinessRecord, ReadinessStatus
from deployctl.persistence.engine import create_async_engine, create_session_factory
from deployctl.persistence.readiness_repository import (
    SqlAlchemyReadinessRepository,
)
from deployctl.service.orchestration.readiness_controller import ReadinessController

type RepositoryOperation[T] = Callable[
    [SqlAlchemyReadinessRepository, ReadinessController],
    Awaitable[T],
]


@pytest.fixture
def database_url(tmp_path) -> str:
    """A throwaway SQLite database shared by the app and the test helpers."""
    return f"sqlite+aiosqlite:///{tmp_path / 'readiness.db'}"


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    app = create_app(config=Config(database_url=database_url))
    with TestClient(app) as test_client:
        yield test_client


def _run_with_repository[T](
    database_url: str,
    operation: RepositoryOperation[T],
) -> T:
    """Run ``operation`` against a fresh repository and controller.

    A dedicated engine is created for the call and disposed afterwards so
    each async block owns the event loop its connections were opened on,
    while still reading the same on-disk database the API uses.
    """

    async def _run() -> T:
        engine = create_async_engine(database_url)
        session_factory = create_session_factory(engine)
        try:
            repository = SqlAlchemyReadinessRepository(
                session_factory=session_factory,
            )
            controller = ReadinessController(
                readiness_repository=repository,
                probe_adapter=NullProbeAdapter(),
            )
            return await operation(repository, controller)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _latest_record(database_url: str, deployment_id: str) -> ReadinessRecord | None:
    async def _operation(
        repository: SqlAlchemyReadinessRepository,
        controller: ReadinessController,
    ) -> ReadinessRecord | None:
        return await repository.get_latest(deployment_id)

    return _run_with_repository(database_url, _operation)


def test_probe_evaluation_persists_readiness_record(
    client: TestClient, database_url: str
) -> None:
    deployment_id = "deploy-probe"

    response = client.post(f"/api/v1/deployments/{deployment_id}/probe", json={})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["deployment_id"] == deployment_id
    assert body["status"] == ReadinessStatus.ready.value
    assert body["healthy"] is True
    assert body["scope_id"] is None
    assert body["source_id"] is None
    assert "observed_at" in body

    persisted = _latest_record(database_url, deployment_id)
    assert persisted is not None
    assert persisted.deployment_id == deployment_id
    assert persisted.status == ReadinessStatus.ready
    assert persisted.details == body["details"]
    assert persisted.scope_id == body["scope_id"]
    assert persisted.source_id == body["source_id"]
    assert persisted.observed_at == datetime.fromisoformat(body["observed_at"])


def test_probe_record_is_visible_through_get(
    client: TestClient, database_url: str
) -> None:
    deployment_id = "deploy-probe-then-get"

    probe_response = client.post(
        f"/api/v1/deployments/{deployment_id}/probe",
        json={"scope_id": "scope-a"},
    )
    assert probe_response.status_code == 201, probe_response.text
    probed = probe_response.json()

    response = client.get(f"/api/v1/deployments/{deployment_id}/readiness")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deployment_id"] == deployment_id
    assert body["status"] == probed["status"]
    assert body["details"] == probed["details"]
    assert body["observed_at"] == probed["observed_at"]
    assert body["scope_id"] == probed["scope_id"]
    assert body["source_id"] == probed["source_id"]


def test_get_readiness_returns_latest_record(
    client: TestClient, database_url: str
) -> None:
    deployment_id = "deploy-latest"
    record = ReadinessRecord(
        deployment_id=deployment_id,
        status=ReadinessStatus.not_ready,
        details={"reason": "probe failed"},
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    async def _seed(
        repository: SqlAlchemyReadinessRepository,
        controller: ReadinessController,
    ) -> None:
        await repository.save(record)

    _run_with_repository(database_url, _seed)

    response = client.get(f"/api/v1/deployments/{deployment_id}/readiness")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deployment_id"] == deployment_id
    assert body["status"] == ReadinessStatus.not_ready.value
    assert body["details"] == {"reason": "probe failed"}

    latest = _run_with_repository(
        database_url,
        lambda repository, controller: controller.get_status(
            deployment_id=deployment_id
        ),
    )
    assert latest is not None
    assert latest.deployment_id == deployment_id
    assert latest.status == ReadinessStatus.not_ready
    assert latest.details == body["details"]
    assert latest.observed_at == datetime.fromisoformat(body["observed_at"])


def test_readiness_for_unknown_deployment_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/deployments/missing-deployment/readiness")

    assert response.status_code == 404
    body = response.json()
    assert "missing-deployment" in body["detail"]
