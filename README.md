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

The environment is configured for async SQLite via `aiosqlite`, and the local
test run uses SQLite. CI also has a Postgres lane that applies this chain to a
`postgres:17` service with `asyncpg`, runs a repository smoke test (save and read
back a deployment, then save and read a readiness record), and then runs the
whole test suite against that server. That includes the endpoint suites
(deployments, promotion, rollback, exposure, readiness), the persistence suite,
and the startup-migration suite, so the schema, the HTTP surface, and the
startup path are exercised on both dialects. `asyncpg` is installed only in
that job rather than declared as a runtime dependency. The `sqlalchemy.url` in
`alembic.ini` is a placeholder; in deployment it should be overridden through
the same configuration path the app uses.

The test fixtures use a throwaway SQLite file by default. Setting
`DEPLOYCTL_TEST_DATABASE_URL` points them at a server database instead, which is
how the Postgres lane runs the suite:

```bash
DEPLOYCTL_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/deployctl \
  pytest -q
```

That fixture drops and recreates the `public` schema before applying the chain,
so every test starts from an empty database and the schema still comes from
Alembic. Tests that need a database with no schema at all — the startup
migration suite does, so it can assert a real cold start and a repeat startup
run — get the same treatment and then start from the empty schema. Point it only
at a database whose contents you are willing to lose.

Schema and row assertions go through SQLAlchemy reflection and bound SQL rather
than `sqlite3` / `sqlite_master`, so the startup and persistence checks are the
same statements on both dialects.

The deployment, promotion, rollback, and exposure routes are `async def`
handlers, so every request runs on the application's event loop and the engine
keeps a real connection pool (no `NullPool`): a connection opened for one
request is reused by the next. That replaced the earlier per-request design, where those handlers were
synchronous and called `asyncio.run`, which forced `NullPool` because a pooled
connection cannot be reused by a closed loop — SQLite tolerates that, `asyncpg`
raises `Event loop is closed`. Going back to a loop per request means bringing
that workaround back with it.

The pool itself is tuned through `Config` rather than left to SQLAlchemy's
defaults:

| Setting | Default | Meaning |
| --- | --- | --- |
| `pool_size` | `5` | Connections kept open in the pool |
| `max_overflow` | `10` | Extra connections allowed above `pool_size` |
| `pool_recycle` | `1800` | Seconds before a pooled connection is replaced on checkout (`-1` disables it; the default keeps a connection from outliving a pooler or load balancer that drops idle ones) |

`build_dependencies` passes them to `create_async_engine`, so a deployment sets
its pool through the same `Config` it already uses for the database URL:

```python
config = Config(
    database_url="postgresql+asyncpg://deploy:secret@db.internal:5432/deployctl",
    pool_size=10,
    max_overflow=20,
    pool_recycle=900,
)
```

A SQLite in-memory URL (`sqlite+aiosqlite:///:memory:`) is served by
SQLAlchemy's `StaticPool` — one connection holding the one database — and that
pool rejects sizing arguments, so those URLs are built without the settings
rather than failing to start.

Tests still use `NullPool` where one test drives a repository from several
`asyncio.run` blocks, and helpers that only read schema or rows open and
dispose one engine per call. That keeps every connection inside the loop that
opened it; the application's own engine is unaffected because its handlers
share a single loop, which is what makes these suites pass on Postgres instead
of only on SQLite.

## Health checks

`GET /health` is a liveness check with no dependencies: it answers
`{"status": "ok"}` without touching the database, so a restart probe does not
fail because the database is briefly unreachable.

`GET /api/v1/system/health` checks the service and the database. It checks a
connection out of the engine pool and runs `SELECT 1`, so a pool that cannot
serve a connection reports `503` on the probe instead of surfacing later as a
failed deployment request:

```json
{
  "ok": false,
  "service": "deployctl",
  "version": "0.1.0",
  "database": "down",
  "error": "OperationalError"
}
```

The probe touches no tables, so a reachable but unmigrated database is healthy;
it answers connectivity, not schema. The body names the exception type only and
never the driver message, which can contain the database URL and its
credentials. When the database answers, the same endpoint returns `200` with
`"database": "up"`.

Point readiness probes at `/api/v1/system/health` and liveness probes at
`/health`; using the database-backed one for both would restart the process
during a database blip.

## Running the tests

```bash
.venv/bin/pytest -q
```

The readiness contract tests are intentionally migration-driven. They apply the
Alembic chain to a fresh SQLite database, run the API against it, and also
assert that downgrading back to `001` removes the `readiness` table cleanly.

### Load testing (opt-in)

`deployctl/tests/test_load.py` starts a real uvicorn server on a loopback port
and drives three scenarios with the engine's connection pool in play: the
database-backed health probe, deployment creation, and deployment lookup. It
reports wall-clock throughput and p50/p95/p99 latency per scenario
(`-s` shows the table on a passing run; pytest otherwise captures it):

```bash
.venv/bin/pytest -q -m load -s
```

The test carries the `load` marker, which the default run excludes, so a plain
`pytest -q` leaves it out. The scenario size is configurable:

| Variable | Default | Meaning |
| --- | --- | --- |
| `DEPLOYCTL_LOAD_CONCURRENCY` | `8` | closed-loop clients per scenario |
| `DEPLOYCTL_LOAD_REQUESTS` | `100` | measured requests per scenario |
| `DEPLOYCTL_LOAD_WARMUP` | `3` | untimed requests before timing starts |
| `DEPLOYCTL_LOAD_REPORT` | unset | write the table as Markdown to this path |

A dedicated `loadtest` CI job runs the harness against `postgres:17` on every
push to `master` and every pull request; the `validate` and `postgres` jobs
still skip it. It publishes the table in the run summary and uploads it as the
`load-report` artifact.

Point the suite at a server database as usual and the same run measures that
database instead of the throwaway SQLite file:

```bash
DEPLOYCTL_TEST_DATABASE_URL=postgresql+asyncpg://... .venv/bin/pytest -q -m load -s
```

SQLite serializes writers, so its `deployment-create` throughput reflects the
single-writer lock; the health and lookup scenarios still measure the real
server and pool. Use Postgres for numbers worth comparing between runs.

### Keeping pull requests up to date

`master` requires branches to be up to date before merging, so every pull
request that is still open when another one merges falls behind and needs an
update. `.github/workflows/update-stale-prs.yml` does that automatically: on
each push to `master` it rebases the open pull requests whose branch is behind,
which re-runs CI on the new head and clears the requirement. It can also be
started by hand from the Actions tab.

Pushes made with the workflow's own token do not start new workflow runs, so an
update made that way would leave the pull request waiting for checks that never
arrive. The job therefore uses a separate token and does nothing until one is
configured. Create a fine-grained personal access token scoped to this
repository with `Contents: read and write` and `Pull requests: read and write`,
then store it as the `PR_UPDATE_TOKEN` Actions secret:

```bash
gh secret set PR_UPDATE_TOKEN --repo <owner>/<repo>
```

Without that secret the job skips every branch and says so in the run summary.
Branches that live in a fork are always skipped, since their authors own the
push. A branch that cannot be rebased cleanly (real conflicts) is not forced:
the job leaves a comment on the pull request saying how to resolve it, and a
later failure refreshes that same comment instead of adding another.

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
