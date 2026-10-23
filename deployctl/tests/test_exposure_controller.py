"""Tests for the exposure orchestration controller.

These tests are intentionally at the contract level. They do not require
a real database or real adapters. They verify that ExposureController is
instantiable, that its result shapes are stable, and that the expected
failure modes are raised.
"""

from __future__ import annotations

import asyncio

import pytest

from deployctl.domain.aggregate.deployment import Deployment
from deployctl.service.orchestration.exposure_controller import (
    ExposureController,
    ExposureRequest,
    ExposureResult,
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


class FakeExposure:
    def begin_limited(self, *, deployment_id, route_id=None, slice_params=None):
        return {"action": "begin_limited", "deployment_id": deployment_id}

    def increase_slice(self, *, deployment_id, route_id=None, slice_params=None):
        return {"action": "increase_slice", "deployment_id": deployment_id}

    def full_exposure(self, *, deployment_id, route_id=None, slice_params=None):
        return {"action": "full_exposure", "deployment_id": deployment_id}

    def retract(self, *, deployment_id, route_id=None, slice_params=None):
        return {"action": "retract", "deployment_id": deployment_id}

    def status(self, *, deployment_id, route_id=None):
        return {"action": "status", "deployment_id": deployment_id}


@pytest.fixture
def controller():
    return ExposureController(
        deployment_repository=FakeRepository(),
        exposure=FakeExposure(),
    )


def _active_deployment():
    return Deployment(
        id="deploy-1",
        description="active deployment",
        artifact_ref="artifact://example@v1",
        status="active",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        metadata={},
    )


def test_exposure_result_shape(controller):
    async def run():
        controller.deployment_repository._deployment = _active_deployment()
        return await controller.shift(
            ExposureRequest(
                deployment_id="deploy-1",
                action="begin_limited",
                slice_params={"pct": 1},
            )
        )

    result = async_run(run)
    assert isinstance(result, ExposureResult)
    assert result.deployment_id == "deploy-1"
    assert result.action == "begin_limited"
    assert result.successful is True
    assert result.current_status == "active"
    assert result.error is None
    assert isinstance(result.adapter_output, dict)


def test_exposure_calls_adapter_for_each_action(controller):
    actions = [
        "begin_limited",
        "increase_slice",
        "full_exposure",
        "retract",
        "status",
    ]
    for action in actions:

        async def run(action=action):
            controller.deployment_repository._deployment = _active_deployment()
            return await controller.shift(
                ExposureRequest(deployment_id="deploy-1", action=action)
            )

        result = async_run(run)
        assert result.successful is True
        assert result.adapter_output["action"] == action


def test_exposure_fails_for_unknown_deployment(controller):
    from deployctl.domain.errors import DeploymentNotFoundError

    async def run():
        return await controller.shift(
            ExposureRequest(
                deployment_id="missing",
                action="begin_limited",
            )
        )

    with pytest.raises(DeploymentNotFoundError):
        async_run(run)


def test_exposure_fails_for_unknown_action(controller):
    from deployctl.domain.errors import ExposureError

    async def run():
        controller.deployment_repository._deployment = _active_deployment()
        return await controller.shift(
            ExposureRequest(
                deployment_id="deploy-1",
                action="not_a_real_action",
            )
        )

    with pytest.raises(ExposureError):
        async_run(run)


def test_exposure_result_contains_adapter_output(controller):
    async def run():
        controller.deployment_repository._deployment = _active_deployment()
        return await controller.shift(
            ExposureRequest(
                deployment_id="deploy-1",
                action="full_exposure",
                slice_params={"pct": 100},
            )
        )

    result = async_run(run)
    assert result.adapter_output["action"] == "full_exposure"
    assert result.adapter_output["deployment_id"] == "deploy-1"
