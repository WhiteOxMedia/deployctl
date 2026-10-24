"""Opt-in load test for the health and deployment endpoints.

This is excluded from the default run by the ``load`` marker (see
``pytest.ini``); run it with::

    pytest -q -m load -s

It starts a real uvicorn server on a loopback port, so the numbers include the
HTTP stack and the engine's connection pool instead of an in-process ASGI
transport. Three scenarios run back to back: the database-backed health probe,
deployment creation, and deployment lookup.

Sizing is configurable through ``DEPLOYCTL_LOAD_CONCURRENCY``,
``DEPLOYCTL_LOAD_REQUESTS`` and ``DEPLOYCTL_LOAD_WARMUP``; setting
``DEPLOYCTL_LOAD_REPORT`` writes the table as Markdown to that path, which is
how CI publishes it in the run summary. Because the suite already accepts
``DEPLOYCTL_TEST_DATABASE_URL``, the same harness can measure SQLite or
Postgres; SQLite serializes writers, so its create numbers describe the
database's single-writer lock rather than the service.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from deployctl.app.config import Config
from deployctl.app.server import create_app
from deployctl.tests._load_harness import (
    ScenarioResult,
    format_markdown_report,
    format_report,
    run_scenario,
)

pytestmark = pytest.mark.load

DEFAULT_CONCURRENCY = 8
DEFAULT_REQUESTS = 100
DEFAULT_WARMUP = 3
STARTUP_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Settings:
    """How much load to apply, and with how many clients."""

    concurrency: int
    requests: int
    warmup: int


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


@pytest.fixture
def settings() -> Settings:
    return Settings(
        concurrency=_env_int(
            "DEPLOYCTL_LOAD_CONCURRENCY", DEFAULT_CONCURRENCY, minimum=1
        ),
        requests=_env_int("DEPLOYCTL_LOAD_REQUESTS", DEFAULT_REQUESTS, minimum=1),
        warmup=_env_int("DEPLOYCTL_LOAD_WARMUP", DEFAULT_WARMUP, minimum=0),
    )


def _wait_until_serving(base_url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        while time.monotonic() < deadline:
            try:
                if client.get("/health").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
    raise RuntimeError(f"the load-test server did not answer on {base_url}")


@pytest.fixture
def load_server(config: Config) -> Iterator[str]:
    """A real uvicorn server for ``config``, on a loopback port."""
    app = create_app(config=config)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, name="uvicorn-loadtest", daemon=True)
    thread.start()

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while not server.started:
        if not thread.is_alive():
            raise RuntimeError("the load-test server exited before it started")
        if time.monotonic() > deadline:
            server.should_exit = True
            raise RuntimeError("the load-test server did not start in time")
        time.sleep(0.05)

    assert server.servers, "uvicorn reported started without a listener"
    sock = server.servers[0].sockets[0]
    base_url = f"http://127.0.0.1:{sock.getsockname()[1]}"

    try:
        _wait_until_serving(base_url)
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=STARTUP_TIMEOUT_SECONDS)
        assert not thread.is_alive(), "the load-test server did not shut down"


def _create_body() -> dict[str, Any]:
    token = uuid.uuid4().hex
    return {
        "deployment_id": f"load-{token}",
        "description": "load-test deployment",
        "artifact_ref": f"artifact://load/{token}@v1",
    }


async def _seed_deployment(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/v1/deployments/",
        json={
            "deployment_id": f"load-seed-{uuid.uuid4().hex}",
            "description": "load-test seed",
            "artifact_ref": "artifact://load/seed@v1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["deployment_id"]


async def _measure(base_url: str, settings: Settings) -> list[ScenarioResult]:
    limits = httpx.Limits(
        max_connections=settings.concurrency,
        max_keepalive_connections=settings.concurrency,
    )
    async with httpx.AsyncClient(
        base_url=base_url, timeout=30.0, limits=limits
    ) as client:
        deployment_id = await _seed_deployment(client)

        scenarios = (
            ("health", "GET", "/api/v1/system/health", None),
            ("deployment-create", "POST", "/api/v1/deployments/", _create_body),
            (
                "deployment-get",
                "GET",
                f"/api/v1/deployments/{deployment_id}",
                None,
            ),
        )
        results = []
        for name, method, path, body in scenarios:
            results.append(
                await run_scenario(
                    client,
                    name=name,
                    method=method,
                    path=path,
                    requests=settings.requests,
                    concurrency=settings.concurrency,
                    warmup=settings.warmup,
                    body=body,
                )
            )
        return results


def test_load_endpoints_report_throughput_and_latency(
    load_server: str, settings: Settings
) -> None:
    results = asyncio.run(_measure(load_server, settings))
    print()
    print(format_report(results, concurrency=settings.concurrency))

    report_path = os.environ.get("DEPLOYCTL_LOAD_REPORT")
    if report_path:
        Path(report_path).write_text(
            format_markdown_report(results, concurrency=settings.concurrency),
            encoding="utf-8",
        )

    failures = [
        (result.name, failure) for result in results for failure in result.failures
    ]
    assert not failures, "requests failed during the load run:\n" + "\n".join(
        f"  {name}: {failure}" for name, failure in failures[:10]
    )

    assert [result.name for result in results] == [
        "health",
        "deployment-create",
        "deployment-get",
    ]
    for result in results:
        assert result.requests == settings.requests
        assert result.wall_seconds > 0
        assert result.requests_per_second > 0
        assert result.p50_ms <= result.p95_ms <= result.p99_ms
