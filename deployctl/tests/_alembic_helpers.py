"""Async Alembic helpers for deployctl test suites.

These helpers apply the project's Alembic migration chain against a fresh
database so that tests exercise the same schema the server applies at startup
instead of using the non-authoritative `Base.metadata.create_all` fallback.

The default target is a throwaway SQLite file. Setting the
``DEPLOYCTL_TEST_DATABASE_URL`` environment variable points the fixtures at a
server database instead, which is how CI runs the same endpoint tests against
Postgres.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

SERVER_DATABASE_URL_ENV = "DEPLOYCTL_TEST_DATABASE_URL"


def is_server_database(database_url: str) -> bool:
    """Whether *database_url* points at a shared server rather than a temp file."""
    return make_url(database_url).get_backend_name() != "sqlite"


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


def reset_database(database_url: str) -> None:
    """Start a server-backed test database from an empty schema at head.

    SQLite tests get a brand-new file per test, so there is nothing to clear.
    A shared server database has no such isolation: each test would otherwise
    inherit rows and revisions from the test before it. Dropping and recreating
    ``public`` gives every test the same starting point as the SQLite fixture,
    and the chain is then applied so the schema still comes from Alembic.
    """
    if not is_server_database(database_url):
        apply_migration_chain(database_url)
        return

    async def _drop_and_recreate_schema() -> None:
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
        finally:
            await engine.dispose()

    asyncio.run(_drop_and_recreate_schema())
    apply_migration_chain(database_url)


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
