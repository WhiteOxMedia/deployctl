from __future__ import annotations

from sqlalchemy import select

from deployctl.domain.readiness import ReadinessRecord
from deployctl.persistence.models import ReadinessModel


class SqlAlchemyReadinessRepository:
    """Async SQLAlchemy implementation of the readiness repository."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def get_latest(self, deployment_id: str) -> ReadinessRecord | None:
        async with self._session_factory() as session:
            stmt = (
                select(ReadinessModel)
                .where(ReadinessModel.deployment_id == deployment_id)
                .order_by(ReadinessModel.timestamp.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return model.to_domain() if model else None

    async def save(self, record: ReadinessRecord) -> None:
        async with self._session_factory() as session:
            model = ReadinessModel.from_domain(record)
            session.add(model)
            await session.commit()
