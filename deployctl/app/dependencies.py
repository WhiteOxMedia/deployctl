"""Application dependency wiring for deployctl."""

from __future__ import annotations

from typing import Any

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
from deployctl.persistence.base import Base
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

    async def create_schema(self) -> None:
        """Create any missing tables.

        Runs inside the application lifespan so the factory stays free of
        blocking I/O and can be called from within a running event loop.
        ``create_all`` only creates what is missing, so this is safe on every
        start.
        """
        if self.engine is None:
            raise RuntimeError(
                "cannot create the schema: dependencies were built without "
                "a database engine"
            )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        """Release the database connection pool."""
        if self.engine is not None:
            await self.engine.dispose()


def build_dependencies(*, config: Config | None = None) -> ApplicationDependencies:
    """Build the application dependency container.

    This only wires objects; it performs no database I/O. The schema is
    created later by :meth:`ApplicationDependencies.create_schema`, which the
    application lifespan awaits on startup.
    """
    if config is None:
        config = Config()

    deps = ApplicationDependencies(config=config)

    engine = create_async_engine(config.engine_url())
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
