"""Domain errors for deployctl."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base class for all domain-layer errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "domain_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} ({self.details})"
        return self.message


class DeploymentNotFoundError(DomainError):
    """Raised when a deployment does not exist."""


class DeploymentStateError(DomainError):
    """Raised when an operation is invalid for the deployment's current state."""


class DeploymentTransitionError(DomainError):
    """Raised when a state transition is not allowed."""


class DeploymentDuplicateError(DomainError):
    """Raised when a deployment already exists."""


class DeploymentIntentError(DomainError):
    """Raised when deployment intent is invalid or incomplete."""


class ArtifactReferenceError(DomainError):
    """Raised when an artifact reference is malformed."""


class OriginTransitionError(DomainError):
    """Raised when an origin transition is not allowed."""


class OriginNotFoundError(DomainError):
    """Raised when an origin register entry does not exist."""


class VersionLedgerError(DomainError):
    """Raised when the version ledger cannot record or resolve an entry."""


class VersionCoherenceError(DomainError):
    """Raised when version coherence is broken."""


class ReadinessError(DomainError):
    """Raised when readiness recording or evaluation is invalid."""


class PromotionError(DomainError):
    """Raised when promotion cannot proceed."""


class ExposureError(DomainError):
    """Raised when an exposure shift cannot be performed."""


class CoordinationError(DomainError):
    """Raised when coordination cannot complete."""


class RollbackNotFoundError(DomainError):
    """Raised when rollback cannot proceed because there is no target."""

    def __init__(
        self,
        *,
        message: str | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        deployment_id: str = "",
        reason: str = "",
    ) -> None:
        super().__init__(
            message=(message or ()),
            code=(code or "rollback_not_available"),
            details=(details or {}),
        )
        self.deployment_id = deployment_id
        self.reason = reason


class RollbackAnchorError(DomainError):
    """Raised when a rollback anchor is missing, weak, or unusable."""

    def __init__(self, deployment_id: str, reason: str) -> None:
        super().__init__(
            message=(
                f"Rollback anchor for deployment "
                f"{deployment_id} is not usable: {reason}"
            ),
            code="rollback_anchor_invalid",
            details={"deployment_id": deployment_id, "reason": reason},
        )
