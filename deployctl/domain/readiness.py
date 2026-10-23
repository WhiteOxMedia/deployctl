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

    def with_status(self, status: ReadinessStatus) -> ReadinessRecord:
        return ReadinessRecord(
            deployment_id=self.deployment_id,
            status=status,
            details=self.details,
            timestamp=self.timestamp,
        )
