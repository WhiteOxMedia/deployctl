"""Shared database helpers for deployctl test suites.

These helpers apply the project's Alembic migration chain against a fresh
database so that tests exercise the same schema the server applies at startup
instead of using the non-authoritative `Base.metadata.create_all` fallback.

The default target is a throwaway SQLite file. Setting the
``DEPLOYCTL_TEST_DATABASE_URL`` environment variable points the fixtures at a
server database instead, which is how CI runs the same tests against Postgres.

Everything here is dialect-neutral on purpose. The suites that inspect schema
and rows (startup migrations, persistence) must make the same assertions on
SQLite and on Postgres, so they go through SQLAlchemy reflection and bound SQL
rather than ``sqlite3`` and ``sqlite_master``.
"""

from __future__ import annotations

import asyncio
import os
import queue
import threading
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect, text
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


async def _drop_and_recreate_public_schema(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


def reset_schema(database_url: str) -> None:
    """Leave *database_url* with no schema at all.

    A SQLite test database is a throwaway file, so deleting it is enough. A
    shared server database has no such isolation: dropping and recreating
    ``public`` gives every test the same empty starting point. Either way the
    schema that follows comes from Alembic, never from ORM metadata.
    """
    if not is_server_database(database_url):
        database_path = make_url(database_url).database
        if database_path and database_path != ":memory:":
            Path(database_path).unlink(missing_ok=True)
        return

    asyncio.run(_drop_and_recreate_public_schema(database_url))


def reset_database(database_url: str) -> None:
    """Start a test database from an empty schema at head.

    SQLite tests get a brand-new file per test, so there is nothing to clear.
    A shared server database would otherwise inherit rows and revisions from
    the test before it; this empties it and reapplies the chain so every test
    starts from the same revision it would start from locally.
    """
    reset_schema(database_url)
    apply_migration_chain(database_url)


def blank_database_url(tmp_path: Any) -> str:
    """A database with no schema and no migration revision.

    Under ``DEPLOYCTL_TEST_DATABASE_URL`` this is the shared server database
    emptied back to a bare ``public`` schema, which is what lets the startup
    migration suite exercise a real cold start against Postgres.
    """
    server_url = os.environ.get(SERVER_DATABASE_URL_ENV)
    if server_url:
        reset_schema(server_url)
        return server_url

    return f"sqlite+aiosqlite:///{Path(tmp_path) / 'startup.db'}"


def migrate_to(database_url: str, revision: str) -> None:
    """Migrate a database to an explicit Alembic revision."""
    _run_alembic(lambda: command.upgrade(_load_config_for_url(database_url), revision))


def downgrade_to(database_url: str, revision: str) -> None:
    """Downgrade a database to an explicit Alembic revision."""
    _run_alembic(
        lambda: command.downgrade(_load_config_for_url(database_url), revision)
    )


async def has_table(url: str, table: str) -> bool:
    """Whether *table* exists, asked through reflection so any dialect works."""
    engine = create_async_engine(url)

    def _check(sync_conn: Any) -> bool:
        return inspect(sync_conn).has_table(table)

    try:
        async with engine.connect() as conn:
            return await conn.run_sync(_check)
    finally:
        await engine.dispose()


async def table_names(url: str) -> set[str]:
    """The set of table names in the database at *url*.

    Reflection keeps this working on both SQLite and Postgres, unlike the
    ``sqlite_master`` queries the startup suite used to run directly.
    """
    engine = create_async_engine(url)

    def _names(sync_conn: Any) -> set[str]:
        return set(inspect(sync_conn).get_table_names())

    try:
        async with engine.connect() as conn:
            return await conn.run_sync(_names)
    finally:
        await engine.dispose()


async def alembic_revision(url: str) -> str:
    """The revision ``alembic_version`` currently records for the database."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
    finally:
        await engine.dispose()

    assert row is not None, "alembic_version should have a current revision"
    return row[0]


async def insert_deployment(
    url: str,
    *,
    deployment_id: str,
    description: str,
    artifact_ref: str,
    status: str = "planned",
    created_at: str = "2026-01-01T00:00:00+00:00",
    updated_at: str = "2026-01-01T00:00:00+00:00",
) -> None:
    """Insert a deployment row with plain SQL, as an operator would.

    The timestamps are written explicitly rather than relying on the columns'
    ``CURRENT_TIMESTAMP`` server defaults, which render differently per dialect.
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO deployments"
                    " (id, description, artifact_ref, status, created_at, updated_at)"
                    " VALUES"
                    " (:id, :description, :artifact_ref, :status, :created_at,"
                    " :updated_at)"
                ),
                {
                    "id": deployment_id,
                    "description": description,
                    "artifact_ref": artifact_ref,
                    "status": status,
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
            )
    finally:
        await engine.dispose()


async def deployment_rows(url: str) -> list[tuple[str, str, str, str]]:
    """The deployment rows the startup suite expects to survive a migration run."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT id, description, artifact_ref, status FROM deployments"
                    " ORDER BY id"
                )
            )
            rows = result.fetchall()
    finally:
        await engine.dispose()

    return [(row[0], row[1], row[2], row[3]) for row in rows]


def create_migrated_database_url(tmp_path: Any) -> str:
    """Return a throwaway SQLite URL and apply the migration chain to it."""
    database_path = Path(tmp_path) / "deployctl-test.db"
    url = f"sqlite+aiosqlite:///{database_path}"
    apply_migration_chain(url)
    return url
