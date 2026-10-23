"""Readiness controller.

This is the slice that turns a raw probe call into a decisionable readiness
record. It is intentionally thin so the rest of the rollout engine can
depend on a stable readiness contract without owning probe mechanics.
"""

from __future__ import annotations

from typing import Any

from deployctl.adapters.probe import ProbeAdapter
from deployctl.domain.readiness import ReadinessRecord, ReadinessStatus
from deployctl.persistence.repository import ReadinessRepository


class ReadinessController:
    """Coordinates readiness evaluation and status query for one deployment.

    Parameters
    ----------
    readiness_repository:
        Persistence for the latest readiness record per deployment.
    probe_adapter:
        External probe adapter used to observe deployment health.
    """

    def __init__(
        self,
        *,
        readiness_repository: ReadinessRepository,
        probe_adapter: ProbeAdapter,
    ) -> None:
        self._readiness_repository = readiness_repository
        self._probe_adapter = probe_adapter

    async def evaluate(self, deployment_id: str) -> ReadinessRecord:
        """Run a probe, persist the observation, and return the record."""
        probe_result = self._probe_adapter.execute(
            deployment_id=deployment_id,
        )
        status = _status_from_probe(probe_result)
        record = ReadinessRecord(
            deployment_id=deployment_id,
            status=status,
            details=probe_result.get("detail"),
        )
        await self._readiness_repository.save(record)
        return record

    async def get_status(self, deployment_id: str) -> ReadinessRecord | None:
        """Return the latest readiness record for the deployment, if any."""
        return await self._readiness_repository.get_latest(deployment_id=deployment_id)


def _status_from_probe(probe_result: dict[str, Any]) -> ReadinessStatus:
    if not probe_result.get("healthy", False):
        return ReadinessStatus.not_ready
    return ReadinessStatus.ready
