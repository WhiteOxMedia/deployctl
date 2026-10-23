"""Alembic environment for deployctl.

This environment configures async migration support with `aiosqlite` and uses
the project's declarative `Base` so generated migrations stay aligned with the
real persistence models.

Production schema creation runs through Alembic (via ``alembic upgrade
head``), not through ``ApplicationDependencies.ensure_schema``; the latter is
kept only as a dev-only helper for scratch databases and is explicitly
documented as a non-authoritative fallback.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from deployctl.persistence.base import Base

config = context.config

# ``fileConfig`` replaces handlers on the root logger, which would silently
# discard a caller's logging setup. Embedding callers opt out through
# ``config.attributes``: the server does so to keep uvicorn's loggers usable for
# startup failures, and the test suite does so to keep pytest's capture. A plain
# ``alembic upgrade head`` run keeps the default.
if config.config_file_name is not None and config.attributes.get(
    "configure_logging", True
):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and no DBAPI, issuing DDL
    directly to the migration script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations using an already-established synchronous connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Alembic's default synchronous runner is replaced here with the async path
    so the project can keep using async drivers for migrations.
    """
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
