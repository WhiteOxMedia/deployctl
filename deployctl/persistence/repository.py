"""Repository contracts and the first SQLAlchemy-backed implementation.

This module replaces the earlier in-memory scaffolding with an async
SQLAlchemy `DeploymentRepository`. The rest of the repository contracts are
kept as explicit interfaces so the service layer can continue to depend on
them before those aggregates are implemented.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import async_sessionmaker

from deployctl.domain.aggregate.deployment import Deployment
from deployctl.domain.errors import DeploymentDuplicateError
from deployctl.persistence.models import DeploymentModel


class DeploymentRepository(Protocol):
    """Persistence contract for deployments."""

    async def get_by_id(self, deployment_id: str) -> Deployment | None: ...
    async def save(self, deployment: Deployment) -> Deployment | None: ...
    async def list(
        self, *, limit: int = 50, offset: int = 0
    ) -> Sequence[Deployment]: ...


class SqlAlchemyDeploymentRepository:
    """Async SQLAlchemy implementation of `DeploymentRepository`.

    This version is intentionally scoped to the first vertical slice. It
    assumes the caller supplies an async session factory and that the
    `deployments` table already exists.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def get_by_id(self, deployment_id: str) -> Deployment | None:
        async with self._session_factory() as session:
            statement = (
                sa_select(DeploymentModel)
                .where(DeploymentModel.id == deployment_id)
                .order_by(DeploymentModel.created_at)
                .limit(1)
            )
            result = await session.execute(statement)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return _model_to_deployment(model)

    async def save(self, deployment: Deployment) -> Deployment | None:
        async with self._session_factory() as session:
            existing = await session.get(DeploymentModel, deployment.id)
            if existing is not None:
                raise DeploymentDuplicateError(
                    message=f"deployment already exists: {deployment.id}",
                    details={
                        "key": deployment.id,
                        "existing_id": deployment.id,
                    },
                )

            db_model = _deployment_to_model(deployment)
            session.add(db_model)
            await session.flush()
            result = _model_to_deployment(db_model)
            await session.commit()
            return result

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[Deployment]:
        async with self._session_factory() as session:
            statement = (
                sa_select(DeploymentModel)
                .order_by(DeploymentModel.created_at)
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(statement)
            models = result.scalars().all()
            return [_model_to_deployment(m) for m in models]


def _deployment_to_model(deployment: Deployment) -> DeploymentModel:
    return DeploymentModel(
        id=deployment.id,
        description=deployment.description,
        artifact_ref=deployment.artifact_ref,
        status=deployment.status,
        created_at=deployment.created_at,
        updated_at=deployment.updated_at,
    )


def _model_to_deployment(model: DeploymentModel) -> Deployment:
    return Deployment(
        id=model.id,
        description=model.description,
        artifact_ref=model.artifact_ref,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
        metadata={},
    )


# ---------------------------------------------------------------------------
# Remaining repository contracts (unchanged shape, async-ready signatures)
# ---------------------------------------------------------------------------


class OriginRepository(Protocol):
    """Contract for origin register persistence."""

    async def get_by_path(self, serving_path_id: str) -> Any | None: ...
    async def save(self, origin: Any) -> Any: ...


class VersionLedgerRepository(Protocol):
    """Contract for version ledger persistence."""

    async def get_by_deployment(self, deployment_id: str) -> Any | None: ...
    async def save(self, ledger: Any) -> Any: ...


class ReadinessRepository(Protocol):
    """Contract for readiness aggregate persistence."""

    async def get_by_deployment(self, deployment_id: str) -> Any | None: ...
    async def save(self, aggregate: Any) -> Any: ...


class OperationLogRepository(Protocol):
    """Contract for operation/audit log persistence."""

    async def append(self, entry: dict[str, Any]) -> dict[str, Any]: ...
    async def list_for_deployment(
        self, deployment_id: str, *, limit: int = 50
    ) -> Sequence[dict[str, Any]]: ...


class ExposureEventRepository(Protocol):
    """Contract for exposure event persistence."""

    async def append(self, event: dict[str, Any]) -> dict[str, Any]: ...
    async def list_for_deployment(
        self, deployment_id: str, *, limit: int = 50
    ) -> Sequence[dict[str, Any]]: ...


class TransactionManager(Protocol):
    """Contract for transactional persistence."""

    async def execute(self, action, **context: Any) -> Any: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
