"""Async Alembic helpers for deployctl test suites.

These helpers apply the project's Alembic migration chain against a fresh
SQLite database so that tests exercise the same schema the server applies at
startup instead of using the non-authoritative `Base.metadata.create_all`
fallback.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _run_alembic(fn: Any) -> None:
    """Run an Alembic command in its own thread so `asyncio.run()` stays valid."""

    results: queue.Queue[BaseException | None] = queue.Queue()

    def _target() -> None:
        try:
            fn()
            results.put(None)
        except BaseException as exc:
            results.put(exc)

    thread = threading.Thread(target=_target, name="alembic")
    thread.start()
    thread.join()
    err = results.get()
    if err is not None:
        raise err


def _load_config_for_url(database_url: str) -> AlembicConfig:
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    # Tests own their logging handlers; without this, migrations/env.py's
    # ``fileConfig`` would replace them and swallow captured log records.
    cfg.attributes["configure_logging"] = False
    return cfg


def apply_migration_chain(database_url: str) -> None:
    """Apply the full migration chain against a fresh database."""
    _run_alembic(lambda: command.upgrade(_load_config_for_url(database_url), "head"))


def migrate_to(database_url: str, revision: str) -> None:
    """Migrate a database to an explicit Alembic revision."""
    _run_alembic(lambda: command.upgrade(_load_config_for_url(database_url), revision))


def downgrade_to(database_url: str, revision: str) -> None:
    """Downgrade a database to an explicit Alembic revision."""
    _run_alembic(
        lambda: command.downgrade(_load_config_for_url(database_url), revision)
    )


async def has_table(url: str, table: str) -> bool:
    """Return True if *table* exists in the database at *url*."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table},
            )
            return result.fetchone() is not None
    finally:
        await engine.dispose()


async def table_names(url: str) -> set[str]:
    """Return the set of user table names in the database at *url*."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
            return {row[0] for row in result.fetchall() if row[0] is not None}
    finally:
        await engine.dispose()


def create_migrated_database_url(tmp_path: Any) -> str:
    """Return a throwaway SQLite URL and apply the migration chain to it."""
    database_path = Path(tmp_path) / "deployctl-test.db"
    url = f"sqlite+aiosqlite:///{database_path}"
    apply_migration_chain(url)
    return url
