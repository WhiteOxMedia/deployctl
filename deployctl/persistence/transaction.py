"""Transaction manager contract.

This defines the transactional boundary the service layer can use once a
persistence backend is implemented. Right now it is a contract only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

R = TypeVar("R")


class TransactionManager(Protocol):
    """Contract for transactional persistence."""

    def execute(self, action: Callable[[], R], **context: Any) -> R: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
