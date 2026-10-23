"""Readiness service tests."""

from __future__ import annotations

import pytest

from deployctl.service.readiness.readiness_service import ReadinessService


class TestReadinessService:
    """Tests for ReadinessService."""

    def test_record_readiness_creates_observation(self) -> None:
        service = ReadinessService()
        record = service.record_readiness(
            deployment_id="dep-1",
            probe_id="probe-1",
            healthy=False,
        )
        assert record.deployment_id == "dep-1"
        assert record.probe_id == "probe-1"
        assert record.healthy is False

    def test_record_readiness_updates_latest_observation(self) -> None:
        service = ReadinessService()
        service.record_readiness(
            deployment_id="dep-1",
            probe_id="probe-1",
            healthy=False,
        )
        record = service.record_readiness(
            deployment_id="dep-1",
            probe_id="probe-1",
            healthy=True,
        )
        assert record.healthy is True

    def test_get_readiness_returns_record(self) -> None:
        service = ReadinessService()
        service.record_readiness(
            deployment_id="dep-1",
            probe_id="probe-1",
            healthy=True,
        )
        record = service.get_readiness(deployment_id="dep-1")
        assert record.healthy is True

    def test_get_readiness_raises_when_missing(self) -> None:
        service = ReadinessService()
        with pytest.raises(Exception):
            service.get_readiness(deployment_id="missing")

    def test_get_latest_readiness_returns_latest(self) -> None:
        service = ReadinessService()
        service.record_readiness(
            deployment_id="dep-1",
            probe_id="probe-1",
            healthy=False,
        )
        service.record_readiness(
            deployment_id="dep-1",
            probe_id="probe-1",
            healthy=True,
        )
        record = service.get_latest_readiness(deployment_id="dep-1")
        assert record.healthy is True

    def test_is_readiness_healthy_returns_healthy_flag(self) -> None:
        service = ReadinessService()
        service.record_readiness(
            deployment_id="dep-1",
            probe_id="probe-1",
            healthy=True,
        )
        assert service.is_readiness_healthy(deployment_id="dep-1") is True

    def test_is_readiness_healthy_returns_false_when_unhealthy(
        self,
    ) -> None:
        service = ReadinessService()
        service.record_readiness(
            deployment_id="dep-1",
            probe_id="probe-1",
            healthy=False,
        )
        assert service.is_readiness_healthy(deployment_id="dep-1") is False
