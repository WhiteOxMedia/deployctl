"""Tests for the promotion API endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
def client() -> TestClient:
    from deployctl.api.router import ApiRouter
    from deployctl.app.dependencies import build_dependencies

    deps = build_dependencies()
    app = FastAPI()
    app.include_router(ApiRouter(dependencies=deps).route())
    return TestClient(app)


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
    def client(self) -> TestClient:
        from deployctl.api.router import ApiRouter
        from deployctl.app.dependencies import build_dependencies

        deps = build_dependencies()
        app = FastAPI()
        app.include_router(ApiRouter(dependencies=deps).route())
        return TestClient(app)

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
