"""Application dependency wiring for deployctl."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from deployctl.app.config import Config
from deployctl.app.null_adapters import (
    NullExposureAdapter,
    NullProbeAdapter,
    NullPromotionAdapter,
    NullRegistryAdapter,
)
from deployctl.persistence.readiness_repository import SqlAlchemyReadinessRepository
from deployctl.persistence.repository import (
    DeploymentRepository,
    ExposureEventRepository,
    OperationLogRepository,
    OriginRepository,
    ReadinessRepository,
    SqlAlchemyDeploymentRepository,
    TransactionManager,
    VersionLedgerRepository,
)
from deployctl.service.deployments import deployment_service
from deployctl.service.orchestration.exposure_controller import ExposureController
from deployctl.service.orchestration.promotion import PromotionEngine
from deployctl.service.orchestration.readiness_controller import ReadinessController
from deployctl.service.orchestration.rollback_coordinator import RollbackCoordinator


class ApplicationDependencies:
    """Container for the runtime services and infrastructure the app needs."""

    def __init__(self, config: Config) -> None:
        self.config = config

        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker | None = None

        # Repositories are wired once a persistence backend exists.
        self.deployment_repository: DeploymentRepository | None = None
        self.origin_repository: OriginRepository | None = None
        self.version_ledger_repository: VersionLedgerRepository | None = None
        self.readiness_repository: ReadinessRepository | None = None
        self.operation_log_repository: OperationLogRepository | None = None
        self.exposure_event_repository: ExposureEventRepository | None = None

        self.transaction_manager: TransactionManager | None = None

        # Services
        self.deployment_service: deployment_service.DeploymentService | None = None
        self.exposure_controller: ExposureController | None = None
        self.rollback_coordinator: RollbackCoordinator | None = None
        self.promotion_engine: PromotionEngine | None = None

        # Null adapters used for endpoint wiring during development.
        self._null_exposure_adapter: NullExposureAdapter | None = NullExposureAdapter()
        self._null_registry_adapter: NullRegistryAdapter | None = NullRegistryAdapter()
        self._null_promotion_adapter: NullPromotionAdapter | None = (
            NullPromotionAdapter()
        )  # noqa: E501
        self._null_probe_adapter: NullProbeAdapter | None = NullProbeAdapter()

    def __getitem__(self, name: str) -> Any:
        value = getattr(self, name, None)
        if value is None:
            raise KeyError(f"no dependency named {name!r}")
        return value

    @property
    def probe_adapter(self) -> NullProbeAdapter:
        """The probe adapter used by the readiness controller during development."""
        if self._null_probe_adapter is None:
            raise KeyError("no dependency named 'probe_adapter'")
        return self._null_probe_adapter

    async def check_database(self) -> None:
        """Check that the pool can serve a connection and the database answers.

        This checks a connection out of the engine pool and runs ``SELECT 1``,
        which is what every request path needs. It touches no tables, so a
        reachable but unmigrated database counts as healthy. Failures propagate
        so the caller can turn them into an unhealthy response instead of
        discovering the dead pool on the next deployment request.
        """
        if self.engine is None:
            raise RuntimeError("the database engine is not wired")
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """Release the database connection pool."""
        if self.engine is not None:
            await self.engine.dispose()


def _pool_options(config: Config) -> dict[str, Any]:
    """Engine pool tuning from ``Config``, or none where a pool cannot apply.

    A SQLite in-memory database is served by SQLAlchemy's ``StaticPool`` — one
    connection holding the one database — and that pool rejects sizing
    arguments, so those URLs keep the dialect's default rather than failing to
    build an engine.
    """
    url = make_url(config.engine_url())
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        return {}
    return {
        "pool_size": config.pool_size,
        "max_overflow": config.max_overflow,
        "pool_recycle": config.pool_recycle,
    }


def build_dependencies(*, config: Config | None = None) -> ApplicationDependencies:
    """Build the application dependency container.

    This only wires objects; it performs no database I/O. The runtime relies on
    the Alembic migration chain for its schema (applied by the startup lifespan
    migrations) and never creates or alters tables itself.
    """
    if config is None:
        config = Config()

    deps = ApplicationDependencies(config=config)

    # The deployment, promotion, rollback, and exposure routes are ``async def``
    # handlers, so every request runs on the application's event loop and a
    # pooled connection stays with the loop that opened it. That is what lets
    # the default pool be used here: a per-request ``asyncio.run`` would park a
    # connection on a loop that closes, and asyncpg rejects reusing it (SQLite
    # tolerates it, which is why that defect only ever showed up on a server).
    # The pool is sized from ``Config`` instead of SQLAlchemy's defaults so a
    # deployment can tune it without the app hardcoding a size.
    engine = create_async_engine(config.engine_url(), **_pool_options(config))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    deps.engine = engine
    deps.session_factory = factory

    deps.deployment_repository = SqlAlchemyDeploymentRepository(
        session_factory=factory,
    )
    deps.deployment_service = deployment_service.DeploymentService(
        deployment_repository=deps.deployment_repository,
    )
    deps.exposure_controller = ExposureController(
        deployment_repository=deps.deployment_repository,
        exposure=deps._null_exposure_adapter,
    )
    deps.rollback_coordinator = RollbackCoordinator(
        deployment_repository=deps.deployment_repository,
        registry=deps._null_registry_adapter,
    )
    deps.promotion_engine = PromotionEngine(
        deployment_repository=deps.deployment_repository,
        promotion=deps._null_promotion_adapter,
        registry=deps._null_registry_adapter,
    )

    repo = SqlAlchemyReadinessRepository(session_factory=factory)
    deps.readiness_repository = repo
    deps.readiness_controller = ReadinessController(
        readiness_repository=repo,
        probe_adapter=deps.probe_adapter,
    )
    deps.transaction_manager = None

    return deps


def create_readiness_repository(
    *, session_factory: async_sessionmaker
) -> SqlAlchemyReadinessRepository:
    """Build a readiness repository for direct repository-level tests.

    This exists so tests that only need the readiness database can stay away
    from the full application dependency container.
    """
    return SqlAlchemyReadinessRepository(session_factory=session_factory)
