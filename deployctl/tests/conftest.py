"""Shared pytest fixtures and migration helpers for deployctl tests.

The shared fixture creates a fresh SQLite database and applies the project's
Alembic migration chain to it, so every test runs against the same schema the
server applies at startup instead of relying on the non-authoritative
`Base.metadata.create_all()` fallback.

Because the fixture already owns the schema, the config it hands to the app
disables the lifespan migration run. That keeps the migration chain applied
exactly once per test instead of racing the server startup path.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deployctl.app.config import Config
from deployctl.app.server import create_app


@pytest.fixture
def migrated_database_url(tmp_path: Path) -> str:
    """A throwaway SQLite database with the full Alembic migration chain applied.

    The schema for this database is applied through Alembic so tests run against
    the same migration-created tables the server expects in production.
    """
    database_path = tmp_path / "deployctl-test.db"
    url = f"sqlite+aiosqlite:///{database_path}"
    from deployctl.tests._alembic_helpers import apply_migration_chain

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
