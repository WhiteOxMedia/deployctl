"""API layer error helpers."""

from __future__ import annotations

from typing import Any


def api_error(
    *,
    status_code: int = 500,
    message: str | None = None,
    code: str = "api_error",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal error envelope for API responses."""
    return {
        "error": {
            "status": status_code,
            "message": message or "internal error",
            "code": code,
            "details": details or {},
        }
    }
