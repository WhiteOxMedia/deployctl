"""Exposure adapter interface.

This is a contract for external traffic/exposure control systems. No real
logic yet.
"""

from __future__ import annotations

from typing import Any, Protocol


class ExposureAdapter(Protocol):
    """Contract for shifting traffic exposure for a deployment."""

    def begin_limited(
        self,
        *,
        deployment_id: str,
        route_id: str | None = None,
        slice_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def increase_slice(
        self,
        *,
        deployment_id: str,
        route_id: str | None = None,
        slice_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def full_exposure(
        self,
        *,
        deployment_id: str,
        route_id: str | None = None,
        slice_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def retract(
        self,
        *,
        deployment_id: str,
        route_id: str | None = None,
        slice_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def status(
        self,
        *,
        deployment_id: str,
        route_id: str | None = None,
    ) -> dict[str, Any]: ...
