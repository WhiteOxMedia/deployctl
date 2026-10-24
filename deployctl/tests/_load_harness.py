"""Measurement and reporting for the opt-in load harness.

The harness drives a real uvicorn server (see ``test_load.py``) rather than
``TestClient``: latency measured through an in-process ASGI transport only
describes the test client's own scheduling, not the server and its connection
pool. Keeping the math here separates it from the server fixture, so the
percentile and reporting logic can be tested without opening a socket.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ScenarioResult:
    """What one load scenario measured.

    ``requests`` counts the requests that were timed, so it matches the
    requested total even when some of them failed; percentiles are computed
    over the successful responses only.
    """

    name: str
    requests: int
    failures: tuple[str, ...]
    wall_seconds: float
    p50_ms: float
    p95_ms: float
    p99_ms: float

    @property
    def requests_per_second(self) -> float:
        """Timed requests per wall-clock second, failures included."""
        if self.wall_seconds <= 0:
            return 0.0
        return self.requests / self.wall_seconds


def percentile(values: Sequence[float], percent: float) -> float:
    """Interpolated percentile (0-100) of ``values``.

    With linear interpolation between the two neighbouring ranks, so a small
    sample still gives a stable p95 instead of snapping to the maximum.
    """
    if not 0 <= percent <= 100:
        raise ValueError(f"percent must be between 0 and 100, got {percent}")
    if not values:
        return 0.0

    ordered = sorted(values)
    rank = (len(ordered) - 1) * percent / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def split_work(total: int, workers: int) -> list[int]:
    """Split ``total`` requests over ``workers`` closed-loop clients."""
    if total < 1:
        raise ValueError(f"total must be at least 1, got {total}")
    if workers < 1:
        raise ValueError(f"workers must be at least 1, got {workers}")

    base, remainder = divmod(total, workers)
    return [base + (1 if index < remainder else 0) for index in range(workers)]


async def run_scenario(
    client: httpx.AsyncClient,
    *,
    name: str,
    method: str,
    path: str,
    requests: int,
    concurrency: int,
    warmup: int = 0,
    body: Callable[[], dict[str, Any] | None] | None = None,
) -> ScenarioResult:
    """Drive one endpoint with ``concurrency`` closed-loop clients.

    Each worker sends its share of the requests back to back over the shared
    client, so at most ``concurrency`` requests are in flight. ``warmup``
    requests run first and are excluded from the latency and throughput
    numbers, which keeps a cold pool and the first-request import cost out of
    the percentiles.
    """
    if requests < 1:
        raise ValueError(f"requests must be at least 1, got {requests}")
    if concurrency < 1:
        raise ValueError(f"concurrency must be at least 1, got {concurrency}")
    if warmup < 0:
        raise ValueError(f"warmup must not be negative, got {warmup}")

    failures: list[str] = []
    latencies: list[float] = []

    async def _send(*, measured: bool) -> None:
        payload = body() if body is not None else None
        started = time.perf_counter()
        try:
            response = await client.request(method, path, json=payload)
        except httpx.HTTPError as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            return
        elapsed = time.perf_counter() - started

        if response.status_code >= 400:
            failures.append(
                f"{name}: HTTP {response.status_code} {response.text[:200]}"
            )
            return
        if measured:
            latencies.append(elapsed)

    async def _worker(count: int) -> None:
        for _ in range(count):
            await _send(measured=True)

    for _ in range(warmup):
        await _send(measured=False)

    started_at = time.perf_counter()
    await asyncio.gather(
        *(_worker(count) for count in split_work(requests, concurrency))
    )
    wall_seconds = time.perf_counter() - started_at

    return ScenarioResult(
        name=name,
        requests=requests,
        failures=tuple(failures),
        wall_seconds=wall_seconds,
        p50_ms=percentile(latencies, 50) * 1000,
        p95_ms=percentile(latencies, 95) * 1000,
        p99_ms=percentile(latencies, 99) * 1000,
    )


_REPORT_ROW = "{name:<22} {requests:>8} {failed:>7} {rps:>9} {p50:>8} {p95:>8} {p99:>8}"


def format_report(results: Sequence[ScenarioResult], *, concurrency: int) -> str:
    """Render the load results as a fixed-width table for the terminal."""
    header = _REPORT_ROW.format(
        name="scenario",
        requests="requests",
        failed="failed",
        rps="req/s",
        p50="p50 ms",
        p95="p95 ms",
        p99="p99 ms",
    )
    lines = [
        f"load test: {concurrency} concurrent clients per scenario",
        header,
        "-" * len(header),
    ]
    for result in results:
        lines.append(
            _REPORT_ROW.format(
                name=result.name,
                requests=result.requests,
                failed=len(result.failures),
                rps=f"{result.requests_per_second:.1f}",
                p50=f"{result.p50_ms:.2f}",
                p95=f"{result.p95_ms:.2f}",
                p99=f"{result.p99_ms:.2f}",
            )
        )
    return "\n".join(lines)


def format_markdown_report(
    results: Sequence[ScenarioResult], *, concurrency: int
) -> str:
    """Render the load results as Markdown, for a CI job summary."""
    lines = [
        f"_{concurrency} concurrent clients per scenario._",
        "",
        "| scenario | requests | failed | req/s | p50 ms | p95 ms | p99 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            f"| {result.name} | {result.requests} | {len(result.failures)} | "
            f"{result.requests_per_second:.1f} | {result.p50_ms:.2f} | "
            f"{result.p95_ms:.2f} | {result.p99_ms:.2f} |"
        )
    return "\n".join(lines) + "\n"
