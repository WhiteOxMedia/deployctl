# deployctl

Deployment control plane skeleton.

The package is importable, builds a FastAPI application, and implements one
end-to-end slice: readiness probe evaluation persisted to SQLite. The remaining
service areas are scaffolding.

## Requirements

- Python 3.14 (declared as `requires-python` in `pyproject.toml`)
- Dependencies are pinned and hash-locked in `requirements.lock`

## Layout

All importable code lives under `deployctl/`:

| Path | Contents |
| --- | --- |
| `deployctl/model/` | Shared, dependency-free primitives |
| `deployctl/domain/` | Errors, state machine, aggregates, value objects |
| `deployctl/policy/` | Policy models, evaluator, snapshot (placeholder) |
| `deployctl/service/` | Orchestration, DTOs, service errors |
| `deployctl/persistence/` | Repositories, mapper, models, transaction contracts |
| `deployctl/adapters/` | External-system adapter interfaces |
| `deployctl/api/` | Router, handlers, schemas |
| `deployctl/app/` | Configuration, dependency wiring, server factory, null adapters |
| `deployctl/events/` | Event types and dispatcher (placeholder) |
| `deployctl/telemetry/` | Logging, metrics, tracing (placeholder) |
| `deployctl/worker/` | Background worker jobs (placeholder) |
| `deployctl/cmd/` | CLI entry point |
| `deployctl/tests/` | Test suite |

Supporting files at the repository root:

| Path | Purpose |
| --- | --- |
| `alembic.ini`, `migrations/` | Alembic environment and revisions (initial `deployments` table) |
| `pyproject.toml` | Project metadata, pinned dependencies, `dev` extras |
| `requirements.lock` | Hash-locked resolution of the runtime and dev dependencies |
| `pytest.ini`, `ruff.toml` | Test discovery and lint configuration |
| `.github/workflows/ci.yml` | Hash-locked install, Ruff, format check, pytest |

The root-level `_*.py`, `diag_*.py` and `run_battery.py` scripts predate the
package and are not part of it.

## Application

`deployctl.app.server.create_app(config=...)` returns a FastAPI app with the API
mounted under `/api/v1`:

- `GET /health`
- `GET /api/v1/system/health`
- `POST /api/v1/deployments/{deployment_id}/probe`
- `GET /api/v1/deployments/{deployment_id}/readiness`

Building the app performs no database I/O, so the factory can be handed
straight to an ASGI server. The schema is created in the application lifespan
on startup, which keeps the factory safe to call from inside a running event
loop:

```
uvicorn --factory deployctl.app.server:create_app --host 127.0.0.1 --port 8000
```

The tests drive the same lifespan by using `TestClient` as a context manager.

## CLI

```
python -m deployctl.cmd.cli server                # serve on 127.0.0.1:8000
python -m deployctl.cmd.cli server --port 9000    # serve on another port
python -m deployctl.cmd.cli worker                # placeholder
python -m deployctl.cmd.cli migrate               # placeholder
```

## Development

```
pip install -e ".[dev]"
pytest -q
ruff check deployctl tests
ruff format --check deployctl tests
alembic upgrade head                  # apply migrations to the local SQLite database
```
