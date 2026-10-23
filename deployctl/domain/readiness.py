"""Domain model for readiness records.

Readiness is the slice that turns probe observations into a decisionable
record for a deployment. This module defines the smallest faithful model
we can act on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ReadinessStatus(Enum):
    """The decisionable readiness state for a deployment."""

    unknown = "unknown"
    ready = "ready"
    not_ready = "not_ready"


@dataclass
class ReadinessRecord:
    """A single, persisted readiness observation for one deployment."""

    deployment_id: str
    status: ReadinessStatus
    details: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    observed_at: datetime = field(
        compare=False, default_factory=lambda: datetime.now(UTC)
    )
    scope_id: str | None = field(compare=False, default=None)
    source_id: str | None = field(compare=False, default=None)

    def with_status(self, status: ReadinessStatus) -> ReadinessRecord:
        return ReadinessRecord(
            deployment_id=self.deployment_id,
            status=status,
            details=self.details,
            timestamp=self.timestamp,
            observed_at=self.observed_at,
            scope_id=self.scope_id,
            source_id=self.source_id,
        )
