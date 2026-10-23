"""Readiness aggregate implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from deployctl.domain.errors import ReadinessError


@dataclass
class ReadinessObservation:
    """A single readiness observation for a probe at a point in time."""

    probe_id: str
    healthy: bool
    observed_at: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReadinessAggregate:
    """Readiness aggregate for a single deployment."""

    deployment_id: str
    probe_id: str
    healthy: bool
    observed_at: str
    detail: dict[str, Any] = field(default_factory=dict)
    _observations: list[ReadinessObservation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.deployment_id:
            raise ValueError("ReadinessAggregate.deployment_id must be non-empty")
        if not self.probe_id:
            raise ValueError("ReadinessAggregate.probe_id must be non-empty")
        if not self.observed_at:
            self.observed_at = datetime.now(UTC).isoformat()

    def record(
        self,
        *,
        probe_id: str,
        healthy: bool,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not probe_id:
            raise ReadinessError(
                message="probe_id is required",
                code="readiness_record_invalid",
                details={
                    "deployment_id": self.deployment_id,
                    "probe_id": probe_id,
                },
            )
        observation = ReadinessObservation(
            probe_id=probe_id,
            healthy=healthy,
            observed_at=datetime.now(UTC).isoformat(),
            detail=detail or {},
        )
        self._observations.append(observation)
        self.probe_id = probe_id
        self.healthy = healthy
        self.observed_at = observation.observed_at
        self.detail = observation.detail
