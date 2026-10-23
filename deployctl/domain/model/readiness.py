"""Readiness model types for the deployctl domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ReadinessSnapshot:
    """A snapshot of readiness state for a deployment."""

    deployment_id: str
    probe_id: str
    healthy: bool
    observed_at: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.deployment_id:
            raise ValueError("ReadinessSnapshot.deployment_id must be non-empty")
        if not self.probe_id:
            raise ValueError("ReadinessSnapshot.probe_id must be non-empty")
        if not self.observed_at:
            self.observed_at = datetime.now(UTC).isoformat()
