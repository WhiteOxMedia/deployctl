"""Tests for readiness gating in the rollout orchestrators."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.readiness import ReadinessRecord, ReadinessStatus
from deployctl.service.orchestration.exposure_controller import (
    ExposureController,
    ExposureNotReadyError,
    ExposureRequest,
)
from deployctl.service.orchestration.promotion_engine import (
    PromotionEngine,
    PromotionEntry,
    PromotionNotReadyError,
)
from deployctl.service.orchestration.readiness_controller import ReadinessController
from deployctl.service.orchestration.rollback_coordinator import (
    RollbackCoordinator,
    RollbackRequest,
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

    def restore(self, *, serving_path_id, previous_serving, deployment_run_id):
        return {
            "serving_path_id": serving_path_id,
            "previous_serving": previous_serving,
            "deployment_run_id": deployment_run_id,
            "restored": True,
        }


class FakeProbe:
    def __init__(self, healthy=True, detail=None):
        self._healthy = healthy
        self._detail = detail or {}

    def execute(self, *, deployment_id, scope_id=None, source_id=None, params=None):
        return {"healthy": self._healthy, "detail": self._detail}


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


def _ready_record(
    *,
    deployment_id="deploy-1",
    status=ReadinessStatus.ready,
    observed_at=None,
):
    observed_at = observed_at or datetime(2026, 1, 1, tzinfo=UTC)
    return ReadinessRecord(
        deployment_id=deployment_id,
        status=status,
        details={"why": "probe said so"},
        observed_at=observed_at,
    )


def test_promotion_requires_readiness_when_ready_record_exists():
    controller = ReadinessController(
        readiness_repository=FakeReadinessRepository(
            _ready_record(status=ReadinessStatus.ready)
        ),
        probe_adapter=FakeProbe(healthy=True),
    )
    engine = PromotionEngine(
        deployment_repository=FakeRepository(),
        placement=FakePlacement(),
        exposure=FakeExposure(),
        artifact=FakeArtifact(),
        registry=FakeRegistry(),
        state_machine=FakeStateMachine(),
        readiness_controller=controller,
    )

    async def run():
        entry = PromotionEntry(
            deployment_id="deploy-1",
            reason="planned -> promoted",
            target_status="promoted",
        )
        engine.deployment_repository._deployment = _planned_deployment()
        return await engine.promote(entry)

    result = async_run(run)
    assert result.successful is True
    assert result.readiness_status == ReadinessStatus.ready.value


def test_promotion_blocked_when_readiness_says_not_ready():
    controller = ReadinessController(
        readiness_repository=FakeReadinessRepository(
            _ready_record(status=ReadinessStatus.not_ready)
        ),
        probe_adapter=FakeProbe(healthy=False),
    )
    engine = PromotionEngine(
        deployment_repository=FakeRepository(),
        placement=FakePlacement(),
        exposure=FakeExposure(),
        artifact=FakeArtifact(),
        registry=FakeRegistry(),
        state_machine=FakeStateMachine(),
        readiness_controller=controller,
    )

    async def run():
        entry = PromotionEntry(
            deployment_id="deploy-1",
            reason="planned -> promoted",
            target_status="promoted",
        )
        engine.deployment_repository._deployment = _planned_deployment()
        return await engine.promote(entry)

    with pytest.raises(PromotionNotReadyError) as caught:
        async_run(run)

    assert caught.value.code == "promotion_not_ready"
    assert caught.value.details["deployment_id"] == "deploy-1"
    assert caught.value.details["readiness_status"] == ReadinessStatus.not_ready.value


def test_promotion_allowed_when_readiness_wire_not_provided():
    engine = PromotionEngine(
        deployment_repository=FakeRepository(),
        placement=FakePlacement(),
        exposure=FakeExposure(),
        artifact=FakeArtifact(),
        registry=FakeRegistry(),
        state_machine=FakeStateMachine(),
        readiness_controller=None,
    )

    async def run():
        entry = PromotionEntry(
            deployment_id="deploy-1",
            reason="planned -> promoted",
            target_status="promoted",
        )
        engine.deployment_repository._deployment = _planned_deployment()
        return await engine.promote(entry)

    result = async_run(run)
    assert result.successful is True
    assert result.readiness_status is None


def test_exposure_requires_readiness_when_ready_record_exists():
    controller = ReadinessController(
        readiness_repository=FakeReadinessRepository(
            _ready_record(status=ReadinessStatus.ready)
        ),
        probe_adapter=FakeProbe(healthy=True),
    )
    exposure = ExposureController(
        deployment_repository=FakeRepository(),
        exposure=FakeExposure(),
        readiness_controller=controller,
    )

    async def run():
        exposure.deployment_repository._deployment = _planned_deployment()
        return await exposure.shift(
            ExposureRequest(
                deployment_id="deploy-1",
                action="begin_limited",
                slice_params={"pct": 1},
            )
        )

    result = async_run(run)
    assert result.successful is True
    assert result.readiness_status == ReadinessStatus.ready.value


def test_exposure_blocked_when_readiness_says_not_ready():
    controller = ReadinessController(
        readiness_repository=FakeReadinessRepository(
            _ready_record(status=ReadinessStatus.not_ready)
        ),
        probe_adapter=FakeProbe(healthy=False),
    )
    exposure = ExposureController(
        deployment_repository=FakeRepository(),
        exposure=FakeExposure(),
        readiness_controller=controller,
    )

    async def run():
        exposure.deployment_repository._deployment = _planned_deployment()
        return await exposure.shift(
            ExposureRequest(
                deployment_id="deploy-1",
                action="begin_limited",
            )
        )

    with pytest.raises(ExposureNotReadyError) as caught:
        async_run(run)

    assert caught.value.code == "exposure_not_ready"
    assert caught.value.details["deployment_id"] == "deploy-1"
    assert caught.value.details["readiness_status"] == ReadinessStatus.not_ready.value


def test_exposure_allowed_when_readiness_wire_not_provided():
    exposure = ExposureController(
        deployment_repository=FakeRepository(),
        exposure=FakeExposure(),
        readiness_controller=None,
    )

    async def run():
        exposure.deployment_repository._deployment = _planned_deployment()
        return await exposure.shift(
            ExposureRequest(
                deployment_id="deploy-1",
                action="begin_limited",
            )
        )

    result = async_run(run)
    assert result.successful is True
    assert result.readiness_status is None


def test_rollback_does_not_block_when_readiness_says_not_ready():
    controller = ReadinessController(
        readiness_repository=FakeReadinessRepository(
            _ready_record(status=ReadinessStatus.not_ready)
        ),
        probe_adapter=FakeProbe(healthy=False),
    )
    coordinator = RollbackCoordinator(
        deployment_repository=FakeRepository(),
        registry=FakeRegistry(),
        readiness_controller=controller,
    )

    async def run():
        coordinator.deployment_repository._deployment = _planned_deployment()
        return await coordinator.rollback(
            RollbackRequest(
                deployment_id="deploy-1",
                reason="probe says not ready",
            )
        )

    result = async_run(run)
    assert result.successful is True
    assert result.readiness_status == ReadinessStatus.not_ready.value
    assert result.restored_to == "artifact://example@v1"


def test_rollback_carries_readiness_context_when_ready():
    controller = ReadinessController(
        readiness_repository=FakeReadinessRepository(
            _ready_record(status=ReadinessStatus.ready)
        ),
        probe_adapter=FakeProbe(healthy=True),
    )
    coordinator = RollbackCoordinator(
        deployment_repository=FakeRepository(),
        registry=FakeRegistry(),
        readiness_controller=controller,
    )

    async def run():
        coordinator.deployment_repository._deployment = _planned_deployment()
        return await coordinator.rollback(
            RollbackRequest(
                deployment_id="deploy-1",
                reason="rollback with readiness context",
            )
        )

    result = async_run(run)
    assert result.successful is True
    assert result.readiness_status == ReadinessStatus.ready.value


def test_rollback_works_when_readiness_wire_not_provided():
    coordinator = RollbackCoordinator(
        deployment_repository=FakeRepository(),
        registry=FakeRegistry(),
        readiness_controller=None,
    )

    async def run():
        coordinator.deployment_repository._deployment = _planned_deployment()
        return await coordinator.rollback(
            RollbackRequest(
                deployment_id="deploy-1",
                reason="rollback without readiness wire",
            )
        )

    result = async_run(run)
    assert result.successful is True
    assert result.readiness_status is None


class FakeReadinessRepository:
    def __init__(self, record=None):
        self._record = record
        self._saved: Any = None

    async def get_latest(self, deployment_id):
        return self._record

    async def save(self, record):
        self._saved = record
