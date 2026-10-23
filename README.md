# deployctl

A minimal deployment control plane skeleton.

## Repository layout

* `deployctl/app/` — FastAPI application wiring, config, and the dependency
  container.
* `deployctl/api/` — FastAPI routes, request / response schemas, and auth.
* `deployctl/persistence/` — SQLAlchemy models, repositories, and the engine
  factory.
* `deployctl/service/` — orchestration and domain services built on top of the
  repositories.
* `domain/` — plain domain types shared across the rest of the project.
* `migrations/` — Alembic migration chain owned by the Django-less ORM layer.

## Running the server locally

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn deployctl.app.server:create_app --factory --reload
```

The server applies the Alembic chain during startup, before it serves traffic,
so a fresh database is brought to head automatically. Running
`alembic upgrade head` first remains a safe no-op and is still what a deploy
pipeline should do; the runtime repeats the same upgrade against the same
`Config` URL and aborts startup if it fails rather than serving a partially
migrated schema. Tables come only from the migration chain — nothing in the
application calls `Base.metadata.create_all()` — so there is no ORM fallback to
drift away from the migration history. For a throwaway database, point
`Config` at a new file and let startup apply the chain, or run
`alembic upgrade head` yourself.

## Migrations

The authoritative schema upgrade path is Alembic.

```bash
alembic upgrade head
alembic current
alembic downgrade -1
```

The migration chain lives in `migrations/`. `001_create_deployments` creates
the `deployments` table. `002_create_readiness_table` creates the `readiness`
table with the explicit `observed_at`, `scope_id`, and `source_id` columns so
the readiness controller can persist and expose the values it forwards from the
probe evaluation.

The environment is configured for async SQLite via `aiosqlite`, and that is the
only driver the test suite exercises. Every migration test runs against SQLite;
nothing here verifies the chain against the async driver used in production, so
treat that path as unproven until a run against the real database has been
done. The `sqlalchemy.url` in `alembic.ini` is a placeholder; in deployment it
should be overridden through the same configuration path the app uses.

## Running the tests

```bash
.venv/bin/pytest -q
```

The readiness contract tests are intentionally migration-driven. They apply the
Alembic chain to a fresh SQLite database, run the API against it, and also
assert that downgrading back to `001` removes the `readiness` table cleanly.

## Overriding the database URL for migrations and the app

The app uses `deployctl.app.config.Config` for its database URL. The same URL
should be used for Alembic so migrations and the running app target the same
database. The `sqlalchemy.url` in `alembic.ini` is only a local placeholder; it
is not the production driver and it should not be edited to hardcode one.

The intended override path is to build a `Config` from the same source of
truth the app uses in deployment and hand that URL to Alembic explicitly, both
in the deploy pipeline and inside the server's startup migrations.

Deploy pipeline example
------------------------

```python
from deployctl.app.config import Config
from alembic.config import Config as AlembicConfig
from alembic import command

# Replace this with whatever source your deploy pipeline already trusts.
database_url = get_deploy_database_url()

config = Config(database_url=database_url)
alembic_cfg = AlembicConfig("alembic.ini")
alembic_cfg.set_main_option("sqlalchemy.url", config.engine_url())
command.upgrade(alembic_cfg, "head")
```

`alembic.ini` stays a placeholder. The important part is that Alembic is
started with the same URL the app would use from `Config.engine_url()`, not with
a driver hardcoded into `alembic.ini`.

Server startup example
----------------------

The server applies the same override before it starts serving traffic. That is
the `alembic upgrade head` run wired through `Config.engine_url()` in
`deployctl.app.server:_apply_migrations`. The run is controlled by
`Config.apply_migrations_on_startup`, which defaults to `True`; tests set it to
`False` because their fixture has already applied the chain to the throwaway
database.

Console
-------

### Startup migration failure

Startup migrations run inside the application lifespan, before the first
request is served. If the chain fails, the error propagates out of the lifespan
and the process exits instead of serving traffic against a partially migrated
schema. The failure is re-raised as a labelled `RuntimeError` that names the
target database:

```text
RuntimeError: failed to apply Alembic migrations to sqlite+aiosqlite:///./deployctl.db: <original error>
```

Credentials are redacted in that message, so a URL such as
`postgresql+asyncpg://deploy:supersecret@db.internal:5432/deployctl` is reported
as `postgresql+asyncpg://deploy:***@db.internal:5432/deployctl`. URLs without a
password, including local SQLite paths, are shown verbatim so the path stays
readable. The original exception is attached as the cause, so the full driver
traceback is still available above the labelled line.

uvicorn treats the escaping exception as a startup failure: it prints
`ERROR: Application startup failed. Exiting.` after the traceback and exits
with status **3** (verified with uvicorn 0.51.0), so supervisors and `set -e`
scripts see a failed start rather than a half-live process. The server does not
reconfigure logging while it migrates, so the uvicorn handlers that print that
traceback stay in place.

A database that is already at head is a no-op: re-running startup migrations
emits no upgrade records and leaves the existing tables and rows untouched.
Alembic's INFO records are only displayed if the `alembic` logger is configured
to show them; the server deliberately leaves logging configuration to the
application. Cold starts (no database file yet) are migrated to head before the
first request in the same way.

### Readiness table missing

This should only happen when startup migrations were disabled, for example
`Config(database_url=..., apply_migrations_on_startup=False)` or a test fixture
that forgot to apply the chain. In that case the first request that needs the
`readiness` table fails instead of the server creating the schema on its own;
migrate the database with `alembic upgrade head` or turn startup migrations
back on.

### `alembic.ini` placeholder

If you see a local URL in `alembic.ini`, that is only the local placeholder.
Do not edit it to hardcode a production driver. Override the URL at runtime
through `Config.engine_url()` instead.

The same `Config(database_url=...)` pattern is also how the app is
parameterized locally and in tests; the migration runner should follow that
instead of inventing its own URL handling.

## Env and secrets

This skeleton does not yet gate anything behind env vars. When it does, the
database URL and any adapter keys should come from configuration, not from
hardcoded defaults or from the migration runner.
