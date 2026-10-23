"""Artifact adapter interface.

This is a contract for external artifact registries/resolution systems. No
real logic yet.
"""

from __future__ import annotations

from typing import Any, Protocol


class ArtifactAdapter(Protocol):
    """Contract for resolving and validating artifact references."""

    def resolve(self, *, ref: str) -> dict[str, Any]: ...

    def validate(
        self,
        *,
        ref: str,
        expected_version: str | None = None,
    ) -> dict[str, Any]: ...

    def metadata(self, *, ref: str) -> dict[str, Any]: ...
