"""Persistence mapper contracts.

These define the mapping contracts between domain aggregates and their stored
representation. Implementations live in the persistence layer once a storage
backend is chosen.
"""

from __future__ import annotations

from typing import Any, Protocol

from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.aggregate.origin_register import OriginRegister
from deployctl.domain.aggregate.readiness import ReadinessAggregate
from deployctl.domain.aggregate.version_ledger import VersionLedger


class DeploymentMapper(Protocol):
    """Maps Deployment aggregate <-> persisted representation."""

    def to_document(self, aggregate: Deployment) -> dict[str, Any]: ...
    def from_document(self, document: dict[str, Any]) -> Deployment: ...


class OriginMapper(Protocol):
    """Maps OriginRegister aggregate <-> persisted representation."""

    def to_document(self, aggregate: OriginRegister) -> dict[str, Any]: ...
    def from_document(self, document: dict[str, Any]) -> OriginRegister: ...


class VersionLedgerMapper(Protocol):
    """Maps VersionLedger aggregate <-> persisted representation."""

    def to_document(self, aggregate: VersionLedger) -> dict[str, Any]: ...
    def from_document(self, document: dict[str, Any]) -> VersionLedger: ...


class ReadinessMapper(Protocol):
    """Maps ReadinessAggregate aggregate <-> persisted representation."""

    def to_document(self, aggregate: ReadinessAggregate) -> dict[str, Any]: ...
    def from_document(self, document: dict[str, Any]) -> ReadinessAggregate: ...


class OperationLogMapper(Protocol):
    """Maps operation log entries <-> persisted representation."""

    def to_document(self, entry: dict[str, Any]) -> dict[str, Any]: ...
    def from_document(self, document: dict[str, Any]) -> dict[str, Any]: ...


class ExposureEventMapper(Protocol):
    """Maps exposure events <-> persisted representation."""

    def to_document(self, event: dict[str, Any]) -> dict[str, Any]: ...
    def from_document(self, document: dict[str, Any]) -> dict[str, Any]: ...
