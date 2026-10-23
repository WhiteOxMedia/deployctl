from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from deployctl.persistence.base import Base

if TYPE_CHECKING:
    from deployctl.domain.readiness import ReadinessRecord


class DeploymentModel(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(String, nullable=False)
    artifact_ref: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="planned")
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.utcnow().isoformat(),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.utcnow().isoformat(),
        onupdate=lambda: datetime.utcnow().isoformat(),
    )

    def __repr__(self) -> str:
        return f"<DeploymentModel id={self.id!r} status={self.status!r}>"


class ReadinessModel(Base):
    __tablename__ = "readiness"

    deployment_id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    timestamp: Mapped[str] = mapped_column(
        String, nullable=False, default=lambda: datetime.utcnow().isoformat()
    )

    observed_at: Mapped[str] = mapped_column(
        String, nullable=False, default=lambda: datetime.now(UTC).isoformat()
    )

    scope_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    source_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    def to_domain(self) -> ReadinessRecord:
        return ReadinessModel._map_to_domain(self)

    @classmethod
    def from_domain(cls, record: ReadinessRecord) -> ReadinessModel:
        return ReadinessModel._map_from_domain(record)

    @staticmethod
    def _map_to_domain(model: ReadinessModel) -> ReadinessRecord:
        from deployctl.domain.readiness import ReadinessRecord, ReadinessStatus

        parsed_details: dict[str, Any] | None = None
        if model.details and model.details != "null":
            try:
                parsed_details = json.loads(model.details)
            except TypeError, ValueError:
                parsed_details = {}

        return ReadinessRecord(
            deployment_id=model.deployment_id,
            status=ReadinessStatus(model.status),
            details=parsed_details,
            timestamp=datetime.fromisoformat(model.timestamp),
            observed_at=datetime.fromisoformat(model.observed_at),
            scope_id=model.scope_id,
            source_id=model.source_id,
        )

    @staticmethod
    def _map_from_domain(record: ReadinessRecord) -> ReadinessModel:
        details_json: str = "null"
        if record.details is not None:
            details_json = json.dumps(record.details)

        return ReadinessModel(
            deployment_id=record.deployment_id,
            status=record.status.value,
            details=details_json,
            timestamp=record.timestamp.isoformat(),
            observed_at=record.observed_at.isoformat(),
            scope_id=record.scope_id,
            source_id=record.source_id,
        )

    def __repr__(self) -> str:
        return (
            "<ReadinessModel "
            f"deployment_id={self.deployment_id!r} "
            f"status={self.status!r}>"
        )

    @staticmethod
    def _serialize_details(details: dict[str, Any] | None) -> str:
        if details is None:
            return "null"
        return json.dumps(details)
