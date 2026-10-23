"""Readiness API handler tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from deployctl.api.router import ApiRouter
from deployctl.app.dependencies import ApplicationDependencies


class TestReadinessEndpoint:
    """Tests for the readiness API endpoints."""

    def test_readiness_wire_error(self) -> None:
        deps = ApplicationDependencies(config=None)
        app = ApiRouter(dependencies=deps).route()
        with TestClient(app) as client:
            response = client.get("/api/v1/readiness/missing")
        assert response.status_code == 501
        assert "readiness.get not implemented" in response.json()["detail"]

    def test_record_readiness_wire_error(self) -> None:
        deps = ApplicationDependencies(config=None)
        app = ApiRouter(dependencies=deps).route()
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/readiness/missing/record",
                json={
                    "deployment_id": "missing",
                    "probe_id": "probe-1",
                    "healthy": True,
                },
            )
        assert response.status_code == 501
        assert "readiness.record not implemented" in response.json()["detail"]
