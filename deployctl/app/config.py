from __future__ import annotations

from typing import Any


class Config:
    """Runtime configuration for deployctl.

    This is intentionally small right now. It exists so the app and the test
    suite can disagree about the database URL without either side reaching
    into environment variables directly.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or self._default_database_url()

    @staticmethod
    def _default_database_url() -> str:
        return "sqlite+aiosqlite:///deployctl.db"

    @property
    def database_url(self) -> str:
        return self._database_url

    def engine_url(self) -> str:
        return self.database_url

    def __repr__(self) -> str:
        return f"Config(database_url={self.database_url!r})"


def apply_config_overrides(**kwargs: Any) -> Config:
    return Config(**kwargs)
