"""deployctl domain aggregates."""

from deployctl.domain.aggregate import (
    deployment,
    origin_register,
    readiness,
    version_ledger,
)

__all__ = ["deployment", "origin_register", "version_ledger", "readiness"]
