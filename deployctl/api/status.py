"""API layer status helpers."""

from __future__ import annotations

from typing import Any

from deployctl.domain.errors import DomainError


class OpenCode:
    """Convenience constants for common OpenAPI-style status codes."""

    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    INTERNAL_ERROR = 500


class OpenStatus:
    """Status enums for hand-rolled error envelopes."""

    OK = "ok"
    ERROR = "error"


class Problem:
    """RFC-ish problem detail envelope."""

    def __init__(
        self,
        *,
        type_: str = "about:blank",
        title: str = "Something went wrong",
        status: int = 500,
        detail: str | None = None,
        instance: str | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        self.type = type_
        self.title = title
        self.status = status
        self.detail = detail
        self.instance = instance
        self.extensions = extensions or {}

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
        }
        if self.detail:
            result["detail"] = self.detail
        if self.instance:
            result["instance"] = self.instance
        result.update(self.extensions)
        return result


def problem(
    *,
    type_: str = "about:blank",
    title: str = "Something went wrong",
    status: int = 500,
    detail: str | None = None,
    instance: str | None = None,
    extensions: dict[str, Any] | None = None,
) -> Problem:
    """Create a ``Problem`` without naming the class directly."""
    return Problem(
        type_=type_,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        extensions=extensions,
    )


def status_from_exception(exc: BaseException) -> int:
    """Map domain/API exceptions onto an HTTP status code."""
    if isinstance(exc, DomainError):
        code = getattr(exc, "code", "")
        if "not_found" in code:
            return 404
        if "invalid" in code or "coherence" in code:
            return 400
        if "conflict" in code:
            return 409
        if "anchor" in code or "not_available" in code:
            return 409
        return 422
    return 500
