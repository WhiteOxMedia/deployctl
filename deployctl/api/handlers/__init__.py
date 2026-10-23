"""deployctl API handlers."""

__all__ = [
    "deployments",
    "exposure",
    "origin",
    "promotion",
    "readiness",
    "rollback",
    "system",
    "version",
]

# readiness module is not imported at package init because it would
# create a circular import with readiness handler module.
readiness = None  # type: ignore[assignment,misc]


def _readiness():
    # Lazy import used by router so readiness handler can be imported
    # without pulling router into module init.
    from deployctl.api.handlers.readiness import ReadinessRouter

    return ReadinessRouter
