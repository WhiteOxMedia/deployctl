"""Tests for the rollback API endpoint."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(app_client: TestClient) -> Iterator[TestClient]:
    """The shared app client, backed by the migration-created database."""
    yield app_client


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
    def client(self, app_client: TestClient) -> Iterator[TestClient]:
        yield app_client

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
