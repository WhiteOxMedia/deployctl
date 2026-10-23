"""Startup migration idempotency tests.

The server lifespan runs ``alembic upgrade head`` when
``Config.apply_migrations_on_startup`` is set. These tests start the real app
against a database that already has the full migration chain applied and assert
the repeated run is a no-op: no "table already exists" failure, no tables
dropped or recreated, and existing rows left intact.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deployctl.app import server as server_module
from deployctl.app.config import Config
from deployctl.app.server import create_app
from deployctl.persistence.base import Base
from deployctl.tests._alembic_helpers import apply_migration_chain

CANARY_ID = "deploy-canary"


def _table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {row[0] for row in rows}


def _alembic_revision(database_path: Path) -> str:
    with sqlite3.connect(database_path) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None, "alembic_version should have a current revision"
    return row[0]


def _deployments(database_path: Path) -> list[tuple[str, str, str, str]]:
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            "SELECT id, description, artifact_ref, status FROM deployments"
        ).fetchall()
    return [(row[0], row[1], row[2], row[3]) for row in rows]


def test_startup_migrations_are_idempotent_on_migrated_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "already-migrated.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"

    apply_migration_chain(database_url)

    tables_before = _table_names(database_path)
    assert {"alembic_version", "deployments", "readiness"} <= tables_before
    assert _alembic_revision(database_path) == "002"

    with sqlite3.connect(database_path) as conn:
        conn.execute(
            "INSERT INTO deployments (id, description, artifact_ref, status)"
            " VALUES (?, ?, ?, ?)",
            (CANARY_ID, "canary", "artifact://canary@v1", "planned"),
        )
    rows_before = _deployments(database_path)
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

        assert _table_names(database_path) == tables_before
        assert _alembic_revision(database_path) == "002"
        assert _deployments(database_path) == rows_before

    assert migration_calls == [database_url, database_url]


def test_startup_migrates_empty_database_to_head(tmp_path: Path) -> None:
    """A cold start must bring an empty database to head before serving."""
    database_path = tmp_path / "cold-start.db"
    assert not database_path.exists()
    database_url = f"sqlite+aiosqlite:///{database_path}"

    app = create_app(config=Config(database_url=database_url))
    with TestClient(app) as client:
        # The lifespan has already completed when the first request is served.
        assert _alembic_revision(database_path) == "002"
        assert {"alembic_version", "deployments", "readiness"} <= _table_names(
            database_path
        )

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

    assert [row[0] for row in _deployments(database_path)] == [deployment_id]


def test_startup_migrations_can_be_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``apply_migrations_on_startup=False`` must skip the lifespan run."""
    database_path = tmp_path / "unmigrated.db"
    database_path.touch()  # a valid but completely empty SQLite database
    database_url = f"sqlite+aiosqlite:///{database_path}"

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
    assert _table_names(database_path) == set()


def test_readiness_fails_without_creating_schema_when_migrations_disabled(
    tmp_path: Path,
) -> None:
    """The documented "readiness table missing" case: fail, never create schema."""
    database_path = tmp_path / "unmigrated.db"
    database_path.touch()  # empty database, no migration chain applied
    database_url = f"sqlite+aiosqlite:///{database_path}"

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
    assert _table_names(database_path) == set()


def test_failing_startup_migration_aborts_before_serving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed migration must abort startup instead of serving a partial schema."""
    database_path = tmp_path / "partial.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"

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

    # The operator-facing error names the database and keeps the cause.
    assert database_url in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, RuntimeError)

    assert _alembic_revision(database_path) == "001"
    assert "readiness" not in _table_names(database_path)


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Startup and request paths must get their schema from Alembic only."""
    database_path = tmp_path / "migrations-only.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"

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
        assert _alembic_revision(database_path) == "002"

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
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An already-migrated database logs context only, no upgrade work."""
    database_path = tmp_path / "already-migrated.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
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
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A cold start logs an upgrade line for each revision it applies."""
    database_path = tmp_path / "cold-start-logged.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"

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
