# deployctl

Deployment control plane skeleton.

This repository is the clean project skeleton for the deployctl control plane.
It is importable but intentionally minimal until the real implementations are
added.

## Architecture

- `model/` — shared, dependency-free primitives.
- `domain/` — domain errors, state machine, aggregates, value objects.
- `policy/` — policy models, evaluator, snapshot (placeholder).
- `service/` — use-case orchestration, DTOs, service errors (placeholder).
- `persistence/` — repository, mapper, transaction contracts and migrations.
- `adapters/` — external-system adapter interfaces (placeholder).
- `api/` — router, auth, middleware, handlers, schemas (placeholder).
- `worker/` — background worker jobs and supervisor (placeholder).
- `events/` — domain event types and dispatcher (placeholder).
- `telemetry/` — logging, metrics, tracing (placeholder).
- `app/` — server wiring placeholders.
- `cmd/` — CLI entry point placeholder.

## Local run

This skeleton does not yet start a server. Once implemented, the intended entry
points are:

- `python -m deployctl.cmd.cli server`
- `python -m deployctl.cmd.cli worker`
- `python -m deployctl.cmd.cli migrate`

## Development

- Formatting and linting: ruff (placeholder config in pyproject.toml)
- Tests: pytest (placeholder config in pyproject.toml)
