"""Readiness service implementation for the deployctl readiness slice."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from deployctl.domain.aggregate.readiness import ReadinessAggregate
from deployctl.domain.errors import ReadinessError


class ReadinessService:
    """Service for readiness observation recording and evaluation.

    This is the first implementation of the readiness slice. It keeps the
    latest readiness observation for each deployment in memory so the API
    handlers can be exercised end-to-end without waiting on the readiness
    persistence contract.
    """

    def __init__(self) -> None:
        self._observations: dict[str, ReadinessAggregate] = {}

    def record_readiness(
        self,
        *,
        deployment_id: str,
        probe_id: str,
        healthy: bool,
        detail: dict[str, Any] | None = None,
    ) -> ReadinessAggregate:
        if not deployment_id:
            raise ReadinessError(
                message="deployment_id is required",
                code="readiness_record_invalid",
                details={"deployment_id": deployment_id},
            )
        if not probe_id:
            raise ReadinessError(
                message="probe_id is required",
                code="readiness_record_invalid",
                details={
                    "deployment_id": deployment_id,
                    "probe_id": probe_id,
                },
            )

        aggregate = self._observations.get(deployment_id)
        if aggregate is None:
            aggregate = ReadinessAggregate(
                deployment_id=deployment_id,
                probe_id=probe_id,
                healthy=healthy,
                observed_at=datetime.now(UTC).isoformat(),
                detail=detail or {},
            )
            self._observations[deployment_id] = aggregate
        else:
            aggregate.record(
                probe_id=probe_id,
                healthy=healthy,
                detail=detail or {},
            )

        return self._observations[deployment_id]

    def get_readiness(self, *, deployment_id: str) -> ReadinessAggregate:
        if not deployment_id:
            raise ReadinessError(
                message="deployment_id is required",
                code="readiness_not_found",
                details={"deployment_id": deployment_id},
            )
        if deployment_id not in self._observations:
            raise ReadinessError(
                message=(f"no readiness record found for deployment {deployment_id}"),
                code="readiness_not_found",
                details={"deployment_id": deployment_id},
            )
        return self._observations[deployment_id]

    def get_latest_readiness(self, *, deployment_id: str) -> ReadinessAggregate:
        return self.get_readiness(deployment_id=deployment_id)

    def is_readiness_healthy(self, *, deployment_id: str) -> bool:
        record = self.get_readiness(deployment_id=deployment_id)
        return record.healthy
