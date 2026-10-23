"""Shared primitive value objects.

These types are dependency-free and intended to be reused across the domain,
service, adapter, and API layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Scope:
    """A named scope that readiness, exposure, or coherence checks target."""

    id: str
    kind: str
    detail: str | None = None
    constraints: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Scope.id must be non-empty")
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("Scope.kind must be non-empty")


@dataclass(frozen=True)
class VersionIdentity:
    """Identity of a specific artifact version."""

    version: str
    ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("VersionIdentity.version must be non-empty")

    def __str__(self) -> str:
        return self.version


@dataclass(frozen=True)
class ActorId:
    """Identity of an actor (operator, service, worker, etc.)."""

    id: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("ActorId.id must be non-empty")

    def __str__(self) -> str:
        return self.id


@dataclass(frozen=True)
class Reason:
    """A structured reason for a domain decision or failure."""

    code: str
    message: str
    detail: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("Reason.code must be non-empty")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("Reason.message must be non-empty")

    def __str__(self) -> str:
        if self.detail:
            return f"{self.code}: {self.message} ({self.detail})"
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a single gated check."""

    status: str
    note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, str) or not self.status.strip():
            raise ValueError("CheckResult.status must be non-empty")


@dataclass(frozen=True)
class ProbeSource:
    """Identity and configuration snapshot of a probe/adapter source."""

    source_id: str
    source_kind: str
    params_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("ProbeSource.source_id must be non-empty")
        if not isinstance(self.source_kind, str) or not self.source_kind.strip():
            raise ValueError("ProbeSource.source_kind must be non-empty")
