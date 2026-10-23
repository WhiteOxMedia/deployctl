"""Probe adapter interface and a planning-time fake.

The real adapter contract is `ProbeAdapter`. `DummyProbeAdapter` implements
the same `execute(...)` shape for tests that plan readiness without wiring a
real adapter, and returns its input parameters back so the recall test can
assert the controller forwarded `scope_id` / `source_id` / `params`.
"""

from __future__ import annotations

from typing import Any, Protocol


class ProbeAdapter(Protocol):
    """Contract for executing a readiness/observation probe."""

    def execute(
        self,
        *,
        deployment_id: str,
        scope_id: str | None = None,
        source_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def resolve_source(self, *, source_id: str) -> dict[str, Any]: ...


class DummyProbeAdapter:
    """A fake probe adapter for planning tests.

    Implements the same ``execute`` contract the ``ReadinessController``
    calls, so planning tests can run without a real adapter, and echoes the
    supplied probe parameters back in the result so the recall test can
    assert ``scope_id`` / ``source_id`` / ``params`` were forwarded.
    """

    def execute(
        self,
        *,
        deployment_id: str,
        scope_id: str | None = None,
        source_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "deployment_id": deployment_id,
            "scope_id": scope_id,
            "source_id": source_id,
            "params": params,
            "healthy": True,
            "detail": None,
        }

    def resolve_source(self, *, source_id: str) -> dict[str, Any]:
        return {"source_id": source_id, "source_type": "dummy"}
