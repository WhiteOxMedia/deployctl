from __future__ import annotations

from typing import Any


class Config:
    """Runtime configuration for deployctl.

    This is intentionally small right now. It exists so the app and the test
    suite can disagree about the database URL without either side reaching
    into environment variables directly.
    """

    def __init__(
        self,
        database_url: str | None = None,
        *,
        apply_migrations_on_startup: bool = True,
    ) -> None:
        self._database_url = database_url or self._default_database_url()
        self._apply_migrations_on_startup = apply_migrations_on_startup

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

    def engine_url(self) -> str:
        return self.database_url

    def __repr__(self) -> str:
        return f"Config(database_url={self.database_url!r})"


def apply_config_overrides(**kwargs: Any) -> Config:
    return Config(**kwargs)
