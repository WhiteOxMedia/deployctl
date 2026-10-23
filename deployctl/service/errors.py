"""Service-layer errors for deployctl."""

from __future__ import annotations

from typing import Any

from deployctl.domain.errors import DomainError


class ServiceError(DomainError):
    """Base class for service-layer errors."""


class CommandError(ServiceError):
    """Raised when an orchestration command cannot be performed."""


class TransactionError(ServiceError):
    """Raised when an orchestration transaction fails."""


class MappingError(ServiceError):
    """Raised when DTO mapping fails."""


class AdapterError(ServiceError):
    """Raised when an adapter call fails."""


class PolicyEvaluationError(ServiceError):
    """Raised when policy evaluation fails or denies an action."""


class EventDispatchError(ServiceError):
    """Raised when event dispatch fails."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "event_dispatch_failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)
