"""Deployment aggregate (placeholder with first-slice shape)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Deployment:
    """A single deployment lifecycle aggregate (placeholder)."""

    id: str
    description: str
    artifact_ref: str
    status: str = "planned"
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Deployment.id must be non-empty")
        if not self.description:
            raise ValueError("Deployment.description must be non-empty")
        if not self.artifact_ref:
            raise ValueError("Deployment.artifact_ref must be non-empty")
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        self.updated_at = self.created_at
