"""Startup migration tests.

The server lifespan runs ``alembic upgrade head`` when
``Config.apply_migrations_on_startup`` is set. These tests start the real app
against a database that already has the full migration chain applied and assert
the repeated run is a no-op: no "table already exists" failure, no tables
dropped or recreated, and existing rows left intact.

The database under test comes from ``blank_database_url``, so the same
assertions run against the throwaway SQLite file locally and against the
Postgres service in CI. Schema and row checks go through SQLAlchemy reflection
and bound SQL rather than ``sqlite3``, so neither dialect is favoured and the
startup path is exercised the same way on both.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from deployctl.app import server as server_module
from deployctl.app.config import Config
from deployctl.app.server import create_app
from deployctl.persistence.base import Base
from deployctl.tests._alembic_helpers import (
    alembic_revision,
    apply_migration_chain,
    blank_database_url,
    deployment_rows,
    insert_deployment,
    table_names,
)

CANARY_ID = "deploy-canary"

EXPECTED_TABLES = {"alembic_version", "deployments", "readiness"}


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """An empty database on whichever dialect this run targets.

    Locally that is a throwaway SQLite file; under
    ``DEPLOYCTL_TEST_DATABASE_URL`` it is the shared server database emptied
    back to a bare ``public`` schema, which is what lets a cold start and a
    repeat startup run be asserted against Postgres too.
    """
    return blank_database_url(tmp_path)


def test_startup_migrations_are_idempotent_on_migrated_database(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    apply_migration_chain(database_url)

    tables_before = asyncio.run(table_names(database_url))
    assert EXPECTED_TABLES <= tables_before
    assert asyncio.run(alembic_revision(database_url)) == "002"

    asyncio.run(
        insert_deployment(
            database_url,
            deployment_id=CANARY_ID,
            description="canary",
            artifact_ref="artifact://canary@v1",
        )
    )
    rows_before = asyncio.run(deployment_rows(database_url))
    assert [row[0] for row in rows_before] == [CANARY_ID]

    # Count the lifespan migration runs while still executing the real ones, so
    # this test also fails if the startup path is skipped entirely.
    real_apply_migrations = server_module._apply_migrations
    migration_calls: list[str] = []

    def _counting_apply_migrations(*, config: Config) -> None:
        migration_calls.append(config.engine_url())
        real_apply_migrations(config=config)

    monkeypatch.setattr(server_module, "_apply_migrations", _counting_apply_migrations)

    # Default config keeps startup migrations on, so the lifespan re-runs the
    # full chain against a database that is already at head.
    for _ in range(2):
        app = create_app(config=Config(database_url=database_url))
        with TestClient(app) as client:
            response = client.get("/api/v1/system/health")
            assert response.status_code == 200, response.text
            assert response.json()["ok"] is True

        assert asyncio.run(table_names(database_url)) == tables_before
        assert asyncio.run(alembic_revision(database_url)) == "002"
        assert asyncio.run(deployment_rows(database_url)) == rows_before

    assert migration_calls == [database_url, database_url]


def test_startup_migrates_empty_database_to_head(database_url: str) -> None:
    """A cold start must bring an empty database to head before serving."""
    assert asyncio.run(table_names(database_url)) == set()

    app = create_app(config=Config(database_url=database_url))
    with TestClient(app) as client:
        # The lifespan has already completed when the first request is served.
        assert asyncio.run(alembic_revision(database_url)) == "002"
        assert EXPECTED_TABLES <= asyncio.run(table_names(database_url))

        assert client.get("/api/v1/system/health").status_code == 200

        created = client.post(
            "/api/v1/deployments/",
            json={
                "description": "cold start deployment",
                "artifact_ref": "artifact://example/cold-start@v1",
            },
        )
        assert created.status_code == 201, created.text
        deployment_id = created.json()["deployment_id"]

        fetched = client.get(f"/api/v1/deployments/{deployment_id}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["deployment_id"] == deployment_id

    assert [row[0] for row in asyncio.run(deployment_rows(database_url))] == [
        deployment_id
    ]


def test_startup_migrations_can_be_disabled(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``apply_migrations_on_startup=False`` must skip the lifespan run."""

    def _forbidden_migration_run(*, config: Config) -> None:
        raise AssertionError(
            "startup migrations ran despite apply_migrations_on_startup=False"
        )

    monkeypatch.setattr(server_module, "_apply_migrations", _forbidden_migration_run)

    config = Config(
        database_url=database_url,
        apply_migrations_on_startup=False,
    )
    app = create_app(config=config)

    with TestClient(app) as client:
        # Startup completes without touching the schema...
        assert client.get("/api/v1/system/health").status_code == 200

    # ...and the empty database is left exactly as it was.
    assert asyncio.run(table_names(database_url)) == set()


def test_readiness_fails_without_creating_schema_when_migrations_disabled(
    database_url: str,
) -> None:
    """The documented "readiness table missing" case: fail, never create schema."""
    config = Config(
        database_url=database_url,
        apply_migrations_on_startup=False,
    )
    app = create_app(config=config)

    # The error surfaces as a server-side failure rather than a 404, because the
    # query itself cannot run without the readiness table.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/deployments/missing-deployment/readiness")
        assert response.status_code == 500, response.text

    # Nothing raced in to create the missing schema.
    assert asyncio.run(table_names(database_url)) == set()


def test_failing_startup_migration_aborts_before_serving(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed migration must abort startup instead of serving a partial schema."""
    real_upgrade = server_module.command.upgrade

    def _failing_upgrade(cfg, revision: str) -> None:
        # Apply only the first revision, then fail mid-chain so the database is
        # left in the partial state a real broken migration could produce.
        real_upgrade(cfg, "001")
        raise RuntimeError("migration failed")

    monkeypatch.setattr(server_module.command, "upgrade", _failing_upgrade)

    app = create_app(config=Config(database_url=database_url))

    # Entering the context runs the lifespan; the failure must propagate so the
    # app never reaches the serving state.
    with pytest.raises(
        RuntimeError, match="failed to apply Alembic migrations"
    ) as excinfo:
        with TestClient(app):
            pass

    # The operator-facing error names the database and keeps the cause. A
    # server URL carries credentials, and the message renders it redacted, so
    # the comparison goes through the same renderer the server uses.
    message = str(excinfo.value)
    assert server_module.describe_database_url(database_url) in message
    password = make_url(database_url).password
    if password is not None:
        assert password not in message
    assert isinstance(excinfo.value.__cause__, RuntimeError)

    assert asyncio.run(alembic_revision(database_url)) == "001"
    assert "readiness" not in asyncio.run(table_names(database_url))


def test_password_bearing_startup_failure_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A startup failure must never leak a database password into the message."""
    database_url = "postgresql+asyncpg://deploy:supersecret@db.internal:5432/deployctl"

    def _failing_upgrade(cfg, revision: str) -> None:
        # Fail before any connection so the test needs no Postgres driver.
        raise RuntimeError("migration failed")

    class _StubDependencies:
        """Minimal container so the app can be built without a DB driver."""

        def __init__(self, config: Config) -> None:
            self.config = config
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    stub = _StubDependencies(Config(database_url=database_url))
    monkeypatch.setattr(server_module, "build_dependencies", lambda *, config: stub)
    monkeypatch.setattr(server_module.command, "upgrade", _failing_upgrade)

    app = create_app(config=stub.config)

    with pytest.raises(
        RuntimeError, match="failed to apply Alembic migrations"
    ) as excinfo:
        with TestClient(app):
            pass

    message = str(excinfo.value)
    assert "supersecret" not in message
    assert "deploy:***@db.internal:5432/deployctl" in message
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert stub.disposed is True


def test_schema_never_created_from_orm_metadata(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Startup and request paths must get their schema from Alembic only."""
    create_all_calls: list[str] = []

    def _forbidden_create_all(*args, **kwargs) -> None:
        create_all_calls.append("Base.metadata.create_all")
        raise AssertionError(
            "schema must come from the Alembic chain, not Base.metadata.create_all"
        )

    monkeypatch.setattr(Base.metadata, "create_all", _forbidden_create_all)

    app = create_app(config=Config(database_url=database_url))
    with TestClient(app) as client:
        # Startup migrated the empty database through Alembic alone.
        assert asyncio.run(alembic_revision(database_url)) == "002"

        created = client.post(
            "/api/v1/deployments/",
            json={
                "description": "migration-only deployment",
                "artifact_ref": "artifact://example/migration-only@v1",
            },
        )
        assert created.status_code == 201, created.text
        deployment_id = created.json()["deployment_id"]
        assert client.get(f"/api/v1/deployments/{deployment_id}").status_code == 200

        probe = client.post(f"/api/v1/deployments/{deployment_id}/probe", json={})
        assert probe.status_code == 201, probe.text
        assert (
            client.get(f"/api/v1/deployments/{deployment_id}/readiness").status_code
            == 200
        )

    assert create_all_calls == []


def test_noop_startup_logs_no_upgrade_lines(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    """An already-migrated database logs context only, no upgrade work."""
    apply_migration_chain(database_url)

    # Drop the records from preparing the database so only startup is measured.
    caplog.clear()
    caplog.set_level(logging.INFO, logger="alembic")

    app = create_app(config=Config(database_url=database_url))
    with TestClient(app) as client:
        assert client.get("/api/v1/system/health").status_code == 200

    messages = [record.getMessage() for record in caplog.records]
    assert [m for m in messages if "Running upgrade" in m] == []
    # The path did run: the context line proves Alembic was invoked.
    assert any("Context impl" in m for m in messages)


def test_cold_start_logs_upgrade_lines(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A cold start logs an upgrade line for each revision it applies."""
    caplog.set_level(logging.INFO, logger="alembic")

    with TestClient(create_app(config=Config(database_url=database_url))):
        pass

    messages = [record.getMessage() for record in caplog.records]
    assert any("Running upgrade" in m and "-> 001" in m for m in messages)
    assert any("Running upgrade" in m and "001 -> 002" in m for m in messages)


def test_migration_error_description_redacts_password() -> None:
    description = server_module.describe_database_url(
        "postgresql+asyncpg://deploy:supersecret@db.internal:5432/deployctl"
    )

    assert "supersecret" not in description
    assert "deploy:***@db.internal:5432/deployctl" in description


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite+aiosqlite:///./deployctl.db",
        "sqlite+aiosqlite:///C:/data/deployctl.db",
    ],
)
def test_migration_error_description_leaves_passwordless_urls_intact(
    database_url: str,
) -> None:
    assert server_module.describe_database_url(database_url) == database_url
