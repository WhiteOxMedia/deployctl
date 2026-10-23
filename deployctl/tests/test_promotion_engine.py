"""Tests for the promotion orchestration engine.

These tests are intentionally at the contract level. They do not require
a real database or real adapters. They verify that PromotionEngine is
instantiable, that its result shapes are stable, and that the expected
failure modes are raised.
"""

from __future__ import annotations

import asyncio

import pytest

from deployctl.domain.aggregate.deployment import Deployment
from deployctl.service.orchestration.promotion_engine import (
    PromotionEngine,
    PromotionEntry,
    PromotionResult,
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


class FakeStateMachine:
    def promotion_target(self, current_status):
        return "promoted"

    def can_transition(self, current_status, target_status):
        if current_status == "planned" and target_status == "promoted":
            return True
        return False


class FakeArtifact:
    def resolve(self, *, ref):
        return {"ref": ref, "ok": True}

    def validate(self, *, ref, expected_version=None):
        return {"ok": True}


class FakePlacement:
    def place(self, **kwargs):
        return {"placed": True, "kwargs": kwargs}


class FakeExposure:
    def begin_limited(self, **kwargs):
        return {"exposed": True, "kwargs": kwargs}


class FakeRegistry:
    def promote(self, **kwargs):
        return {"registry_promoted": True, "kwargs": kwargs}


@pytest.fixture
def engine():
    return PromotionEngine(
        deployment_repository=FakeRepository(),
        placement=FakePlacement(),
        exposure=FakeExposure(),
        artifact=FakeArtifact(),
        registry=FakeRegistry(),
        state_machine=FakeStateMachine(),
    )


def _planned_deployment():
    return Deployment(
        id="deploy-1",
        description="planned deployment",
        artifact_ref="artifact://example@v1",
        status="planned",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        metadata={},
    )


def test_promotion_result_shape(engine):
    async def run():
        entry = PromotionEntry(
            deployment_id="deploy-1",
            reason="planned -> promoted",
            target_status="promoted",
        )
        engine.deployment_repository._deployment = _planned_deployment()
        return await engine.promote(entry)

    result = async_run(run)
    assert isinstance(result, PromotionResult)
    assert result.deployment_id == "deploy-1"
    assert result.successful is True
    assert result.previous_status == "planned"
    assert result.current_status == "promoted"
    assert result.reason == "planned -> promoted"
    assert result.error is None
    assert isinstance(result.steps, dict)


def test_promotion_required_fields(engine):
    async def run():
        entry = PromotionEntry(deployment_id="deploy-1", reason="planned -> promoted")
        engine.deployment_repository._deployment = _planned_deployment()
        return await engine.promote(entry)

    result = async_run(run)
    assert result.successful is True
    assert result.steps is not None
    assert "artifact" in result.steps
    assert "placement" in result.steps
    assert "exposure" in result.steps
    assert "registry" in result.steps


def test_promotion_fails_for_unknown_deployment(engine):
    from deployctl.domain.errors import DeploymentNotFoundError

    async def run():
        entry = PromotionEntry(
            deployment_id="missing",
            reason="planned -> promoted",
        )
        return await engine.promote(entry)

    with pytest.raises(DeploymentNotFoundError):
        async_run(run)


def test_promotion_fails_when_state_machine_forbids(engine):
    from deployctl.service.orchestration.promotion_engine import (
        PromotionNotAllowedError,
    )

    engine.state_machine.can_transition = lambda current_status, target_status: False
    engine.state_machine.promotion_target = lambda current_status: "promoted"

    async def run():
        entry = PromotionEntry(
            deployment_id="deploy-1",
            reason="planned -> promoted",
            target_status="promoted",
        )
        engine.deployment_repository._deployment = _planned_deployment()
        return await engine.promote(entry)

    with pytest.raises(PromotionNotAllowedError):
        async_run(run)


def test_promotion_fails_on_adapter_call_failure(engine):
    from deployctl.service.orchestration.promotion_engine import (
        PromotionStepError,
    )

    class BrokenPlacement:
        def place(self, **kwargs):
            raise RuntimeError("placement unavailable")

    engine.placement = BrokenPlacement()

    async def run():
        entry = PromotionEntry(
            deployment_id="deploy-1",
            reason="planned -> promoted",
            target_status="promoted",
        )
        engine.deployment_repository._deployment = _planned_deployment()
        return await engine.promote(entry)

    with pytest.raises(PromotionStepError):
        async_run(run)


def test_promotion_result_contains_step_outcomes(engine):
    async def run():
        entry = PromotionEntry(
            deployment_id="deploy-1",
            reason="planned -> promoted",
            target_status="promoted",
        )
        engine.deployment_repository._deployment = _planned_deployment()
        return await engine.promote(entry)

    result = async_run(run)
    assert result.steps["artifact"] == {"ref": "artifact://example@v1", "ok": True}
    assert result.steps["placement"]["placed"] is True
    assert result.steps["exposure"]["exposed"] is True
    assert result.steps["registry"]["registry_promoted"] is True


def test_promotion_returns_promotion_result(engine):
    async def run():
        entry = PromotionEntry(
            deployment_id="deploy-1",
            reason="planned -> promoted",
            target_status="promoted",
        )
        engine.deployment_repository._deployment = _planned_deployment()
        return await engine.promote(entry)

    result = async_run(run)
    assert isinstance(result, PromotionResult)
    assert result.deployment_id == "deploy-1"
    assert result.successful is True
    assert result.previous_status == "planned"
    assert result.current_status == "promoted"
    assert result.reason == "planned -> promoted"
    assert result.error is None
    assert isinstance(result.steps, dict)
