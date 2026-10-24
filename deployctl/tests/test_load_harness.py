"""Unit tests for the load harness's measurement and reporting helpers."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from deployctl.tests._load_harness import (
    ScenarioResult,
    format_markdown_report,
    format_report,
    percentile,
    run_scenario,
    split_work,
)


def test_percentile_interpolates_between_neighbouring_ranks() -> None:
    values = [10.0, 20.0, 30.0, 40.0]

    assert percentile(values, 0) == 10.0
    assert percentile(values, 50) == 25.0
    assert percentile(values, 99) == pytest.approx(39.7)
    assert percentile(values, 100) == 40.0


def test_percentile_of_no_samples_is_zero() -> None:
    assert percentile([], 95) == 0.0


def test_percentile_rejects_a_rank_outside_0_100() -> None:
    with pytest.raises(ValueError):
        percentile([1.0], 101)


def test_split_work_gives_every_extra_request_to_an_early_worker() -> None:
    assert split_work(10, 3) == [4, 3, 3]
    assert split_work(2, 5) == [1, 1, 0, 0, 0]
    assert sum(split_work(100, 7)) == 100


def test_split_work_rejects_an_empty_run() -> None:
    with pytest.raises(ValueError):
        split_work(0, 1)
    with pytest.raises(ValueError):
        split_work(10, 0)


def test_scenario_times_successful_requests() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200))

    async def _run() -> ScenarioResult:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://load"
        ) as client:
            return await run_scenario(
                client,
                name="health",
                method="GET",
                path="/health",
                requests=12,
                concurrency=3,
                warmup=2,
            )

    result = asyncio.run(_run())

    assert result.requests == 12
    assert result.failures == ()
    assert result.wall_seconds > 0
    assert result.requests_per_second > 0
    assert result.p50_ms <= result.p95_ms <= result.p99_ms


def test_scenario_reports_failed_responses() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(503, text="unavailable")
    )

    async def _run() -> ScenarioResult:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://load"
        ) as client:
            return await run_scenario(
                client,
                name="health",
                method="GET",
                path="/health",
                requests=3,
                concurrency=1,
            )

    result = asyncio.run(_run())

    assert len(result.failures) == 3
    assert "health: HTTP 503" in result.failures[0]


def test_report_has_a_row_per_scenario() -> None:
    results = [
        ScenarioResult("health", 100, (), 0.5, 2.0, 4.0, 8.0),
        ScenarioResult("deployment-create", 50, ("boom",), 1.0, 10.0, 20.0, 30.0),
    ]

    report = format_report(results, concurrency=8)
    lines = report.splitlines()

    assert lines[0] == "load test: 8 concurrent clients per scenario"
    for heading in ("requests", "failed", "req/s", "p50", "p95", "p99"):
        assert heading in lines[1]

    health = next(line for line in lines if line.startswith("health"))
    assert health.split()[1:3] == ["100", "0"]
    assert "200.0" in health
    assert "2.00" in health
    assert "4.00" in health
    assert "8.00" in health

    create = next(line for line in lines if line.startswith("deployment-create"))
    assert create.split()[1:3] == ["50", "1"]
    assert "50.0" in create


def test_markdown_report_is_a_table() -> None:
    results = [ScenarioResult("health", 100, (), 0.5, 2.0, 4.0, 8.0)]

    markdown = format_markdown_report(results, concurrency=8)
    lines = markdown.splitlines()

    assert lines[0] == "_8 concurrent clients per scenario._"
    assert (
        lines[2]
        == "| scenario | requests | failed | req/s | p50 ms | p95 ms | p99 ms |"
    )
    assert lines[4] == "| health | 100 | 0 | 200.0 | 2.00 | 4.00 | 8.00 |"
    assert markdown.endswith("\n")
