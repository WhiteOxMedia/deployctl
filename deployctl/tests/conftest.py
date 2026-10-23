"""Shared pytest fixtures and migration helpers for deployctl tests.

The shared fixture creates a fresh database and applies the project's Alembic
migration chain to it, so every test runs against the same schema the server
applies at startup instead of relying on the non-authoritative
`Base.metadata.create_all()` fallback.

By default that database is a throwaway SQLite file. When
``DEPLOYCTL_TEST_DATABASE_URL`` is set, the same tests run against that server
database instead; CI uses it to execute the endpoint suite on Postgres. Each
test still starts from an empty schema, because the fixture resets it before
applying the chain.

Because the fixture already owns the schema, the config it hands to the app
disables the lifespan migration run. That keeps the migration chain applied
exactly once per test instead of racing the server startup path.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deployctl.app.config import Config
from deployctl.app.server import create_app
from deployctl.tests._alembic_helpers import (
    SERVER_DATABASE_URL_ENV,
    apply_migration_chain,
    reset_database,
)


@pytest.fixture
def migrated_database_url(tmp_path: Path) -> str:
    """A throwaway database with the full Alembic migration chain applied.

    The schema for this database is applied through Alembic so tests run against
    the same migration-created tables the server expects in production. When
    ``DEPLOYCTL_TEST_DATABASE_URL`` is set that server database is reset and
    reused; otherwise a fresh SQLite file is created per test.
    """
    server_url = os.environ.get(SERVER_DATABASE_URL_ENV)
    if server_url:
        reset_database(server_url)
        return server_url

    database_path = tmp_path / "deployctl-test.db"
    url = f"sqlite+aiosqlite:///{database_path}"
    apply_migration_chain(url)
    return url


@pytest.fixture
def config(migrated_database_url: str) -> Config:
    """Config wired to the migrated throwaway database.

    Startup migrations are disabled because ``migrated_database_url`` has
    already applied the chain.
    """
    return Config(
        database_url=migrated_database_url,
        apply_migrations_on_startup=False,
    )


@pytest.fixture
def app_client(config: Config) -> Iterator[TestClient]:
    """FastAPI TestClient against a fresh, migration-created database."""
    app = create_app(config=config)
    with TestClient(app) as test_client:
        yield test_client
