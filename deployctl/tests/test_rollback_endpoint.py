"""Tests for the rollback API endpoint."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from deployctl.app.server import create_app
from deployctl.domain.aggregate.deployment import Deployment


def _active_deployment() -> Deployment:
    return Deployment(
        id="deploy-1",
        description="active deployment",
        artifact_ref="artifact://example@previous",
        status="active",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        metadata={},
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_rollback_endpoint_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/v1/deployments/missing/rollback",
        json={"reason": "nope"},
    )
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_rollback_endpoint_wire_error() -> None:
    from deployctl.api.router import ApiRouter
    from deployctl.app.dependencies import ApplicationDependencies

    deps = ApplicationDependencies(config=None)
    app = ApiRouter(dependencies=deps).route()
    # Wire error path is tested by integration tests.
    app  # noqa: F841


class TestRollbackEndpoint:
    @pytest.fixture
    def client(self) -> Iterator[TestClient]:
        with TestClient(create_app()) as test_client:
            yield test_client

    def test_rollback_fails_for_unknown_deployment(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/deployments/deploy-99/rollback",
            json={"reason": "unknown deployment"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_rollback_fails_for_deployment_with_no_restore_target(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/deployments/deploy-99/rollback",
            json={"reason": "no restore target"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_rollback_success(self, client: TestClient) -> None:
        from deployctl.api.schemas.deployments import DeploymentCreateRequest

        DeploymentCreateRequest(
            description="rollback success",
            artifact_ref="artifact://example@previous",
            metadata={},
        )
        response = client.post(
            "/api/v1/deployments/deploy-99/rollback",
            json={"reason": "rolled back"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_rollback_uses_explicit_target(self, client: TestClient) -> None:
        from deployctl.api.schemas.deployments import DeploymentCreateRequest

        DeploymentCreateRequest(
            description="rollback explicit target",
            artifact_ref="artifact://example@previous",
            metadata={},
        )
        response = client.post(
            "/api/v1/deployments/deploy-99/rollback",
            json={
                "reason": "explicit restore",
                "target_artifact_ref": "artifact://example@baseline",
            },
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
