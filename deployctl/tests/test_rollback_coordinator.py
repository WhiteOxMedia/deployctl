"""Tests for the rollback orchestration coordinator.

These tests are intentionally at the contract level. They do not require
a real database or real adapters. They verify that RollbackCoordinator is
instantiable, that its result shapes are stable, and that the expected
failure modes are raised.
"""

from __future__ import annotations

import asyncio

import pytest

from deployctl.domain.aggregate.deployment import Deployment
from deployctl.service.orchestration.rollback_coordinator import (
    RollbackCoordinator,
    RollbackRequest,
    RollbackResult,
)


def async_run(callback):
    return asyncio.run(callback())


class FakeRepository:
    def __init__(self, deployment=None):
        self._deployment = deployment

    async def get_by_id(self, deployment_id):
        return self._deployment

    async def save(self, deployment):
        return deployment


class FakeRegistry:
    def restore(self, *, serving_path_id, previous_serving, deployment_run_id):
        return {
            "serving_path_id": serving_path_id,
            "previous_serving": previous_serving,
            "deployment_run_id": deployment_run_id,
            "restored": True,
        }


@pytest.fixture
def coordinator():
    return RollbackCoordinator(
        deployment_repository=FakeRepository(),
        registry=FakeRegistry(),
    )


def _active_deployment():
    return Deployment(
        id="deploy-1",
        description="active deployment",
        artifact_ref="artifact://example@previous",
        status="active",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        metadata={},
    )


def test_rollback_result_shape(coordinator):
    async def run():
        coordinator.deployment_repository._deployment = _active_deployment()
        return await coordinator.rollback(
            RollbackRequest(
                deployment_id="deploy-1",
                reason="failed promote",
            )
        )

    result = async_run(run)
    assert isinstance(result, RollbackResult)
    assert result.deployment_id == "deploy-1"
    assert result.successful is True
    assert result.previous_status == "active"
    assert result.current_status == "rolled_back"
    assert result.reason == "failed promote"
    assert result.restored_to == "artifact://example@previous"
    assert result.error is None
    assert isinstance(result.steps, dict)


def test_rollback_uses_explicit_target_when_provided(coordinator):
    async def run():
        coordinator.deployment_repository._deployment = _active_deployment()
        return await coordinator.rollback(
            RollbackRequest(
                deployment_id="deploy-1",
                reason="explicit restore",
                target_artifact_ref="artifact://example@baseline",
            )
        )

    result = async_run(run)
    assert result.restored_to == "artifact://example@baseline"
    assert result.steps["registry"]["previous_serving"] == "artifact://example@baseline"


def test_rollback_fails_for_unknown_deployment(coordinator):
    from deployctl.domain.errors import DeploymentNotFoundError

    async def run():
        return await coordinator.rollback(
            RollbackRequest(
                deployment_id="missing",
                reason="failed promote",
            )
        )

    with pytest.raises(DeploymentNotFoundError):
        async_run(run)


def test_rollback_fails_when_no_restore_target(coordinator):
    from deployctl.domain.errors import RollbackNotFoundError

    async def run():
        deployment = _active_deployment()
        coordinator.deployment_repository._deployment = deployment
        coordinator._rollback_target = lambda request, deployment: None
        return await coordinator.rollback(
            RollbackRequest(
                deployment_id="deploy-1",
                reason="failed promote",
            )
        )

    with pytest.raises(RollbackNotFoundError):
        async_run(run)


def test_rollback_fails_when_registry_restore_raises(coordinator):
    from deployctl.domain.errors import RollbackAnchorError

    class BrokenRegistry:
        def restore(self, *, serving_path_id, previous_serving, deployment_run_id):
            raise RuntimeError("registry unavailable")

    coordinator.registry = BrokenRegistry()

    async def run():
        coordinator.deployment_repository._deployment = _active_deployment()
        return await coordinator.rollback(
            RollbackRequest(
                deployment_id="deploy-1",
                reason="failed promote",
            )
        )

    with pytest.raises(RollbackAnchorError):
        async_run(run)


def test_rollback_result_contains_restore_steps(coordinator):
    async def run():
        coordinator.deployment_repository._deployment = _active_deployment()
        return await coordinator.rollback(
            RollbackRequest(
                deployment_id="deploy-1",
                reason="failed promote",
                target_artifact_ref="artifact://example@baseline",
            )
        )

    result = async_run(run)
    assert result.steps is not None
    assert result.steps["registry"]["restored"] is True
    assert result.steps["registry"]["previous_serving"] == "artifact://example@baseline"
