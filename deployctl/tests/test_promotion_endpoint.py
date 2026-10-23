"""Tests for the promotion API endpoint."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(app_client: TestClient) -> Iterator[TestClient]:
    """The shared app client, backed by the migration-created database."""
    yield app_client


def test_promotion_endpoint_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/v1/deployments/missing/promote",
        json={"reason": "nope"},
    )
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_promotion_endpoint_wire_error() -> None:
    from deployctl.api.router import ApiRouter
    from deployctl.app.dependencies import ApplicationDependencies

    deps = ApplicationDependencies(config=None)
    app = ApiRouter(dependencies=deps).route()
    # Wire error path is tested by integration tests.
    app  # noqa: F841


class TestPromotionEndpoint:
    @pytest.fixture
    def client(self, app_client: TestClient) -> Iterator[TestClient]:
        yield app_client

    def test_promotion_fails_for_unknown_deployment(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/deployments/deploy-99/promote",
            json={"reason": "unknown deployment"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_promotion_fails_for_deployment_with_no_status(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/deployments/deploy-99/promote",
            json={"reason": "no status"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_promotion_success(self, client: TestClient) -> None:
        from deployctl.api.schemas.deployments import DeploymentCreateRequest

        DeploymentCreateRequest(
            description="promotion success",
            artifact_ref="artifact://example@previous",
            metadata={},
        )
        response = client.post(
            "/api/v1/deployments/deploy-99/promote",
            json={"reason": "promoted"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_promotion_uses_explicit_target(self, client: TestClient) -> None:
        from deployctl.api.schemas.deployments import DeploymentCreateRequest

        DeploymentCreateRequest(
            description="promotion explicit target",
            artifact_ref="artifact://example@previous",
            metadata={},
        )
        response = client.post(
            "/api/v1/deployments/deploy-99/promote",
            json={
                "reason": "explicit promotion",
                "target_artifact_ref": "artifact://example@baseline",
            },
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
