"""deployctl — deployment control plane.

This package is currently a structural skeleton. Domain, service, API,
persistence, worker, and adapter packages are present as importable modules
with placeholder implementations.
"""

from deployctl import (
    adapters,
    api,
    app,
    cmd,
    domain,
    events,
    model,
    persistence,
    policy,
    service,
    telemetry,
    worker,
)

__all__ = [
    "app",
    "api",
    "cmd",
    "domain",
    "events",
    "model",
    "persistence",
    "policy",
    "service",
    "telemetry",
    "worker",
    "adapters",
]
