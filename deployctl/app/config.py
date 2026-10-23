from __future__ import annotations

from typing import Any


class Config:
    """Runtime configuration for deployctl.

    This is intentionally small right now. It exists so the app and the test
    suite can disagree about the database URL without either side reaching
    into environment variables directly.

    It also carries the connection pool tuning, so the pool a deployment runs
    with is a configuration decision instead of whatever SQLAlchemy happens to
    default to.
    """

    def __init__(
        self,
        database_url: str | None = None,
        *,
        apply_migrations_on_startup: bool = True,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_recycle: int = 1800,
    ) -> None:
        self._database_url = database_url or self._default_database_url()
        self._apply_migrations_on_startup = apply_migrations_on_startup
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._pool_recycle = pool_recycle

    @staticmethod
    def _default_database_url() -> str:
        return "sqlite+aiosqlite:///deployctl.db"

    @property
    def database_url(self) -> str:
        return self._database_url

    @property
    def apply_migrations_on_startup(self) -> bool:
        """Whether the application lifespan should run ``alembic upgrade head``.

        Production keeps this on so startup is wired to the same migration path
        as deploys. Tests turn it off because their fixture already applies the
        migration chain to the throwaway database; repeating it would duplicate
        the fixture's work and make schema ownership ambiguous.
        """
        return self._apply_migrations_on_startup

    @property
    def pool_size(self) -> int:
        """Connections kept open in the engine pool."""
        return self._pool_size

    @property
    def max_overflow(self) -> int:
        """Extra connections the pool may open above ``pool_size``."""
        return self._max_overflow

    @property
    def pool_recycle(self) -> int:
        """Seconds before a pooled connection is replaced on checkout.

        ``-1`` disables recycling. The default of 1800 keeps a connection from
        outliving a load balancer or pooler that silently drops idle ones.
        """
        return self._pool_recycle

    def engine_url(self) -> str:
        return self.database_url

    def __repr__(self) -> str:
        return (
            f"Config(database_url={self.database_url!r}, "
            f"pool_size={self.pool_size}, "
            f"max_overflow={self.max_overflow}, "
            f"pool_recycle={self.pool_recycle})"
        )


def apply_config_overrides(**kwargs: Any) -> Config:
    return Config(**kwargs)
