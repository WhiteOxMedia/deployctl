"""Null adapters for deployctl early vertical slice development."""

from __future__ import annotations

from typing import Any

from deployctl.adapters.probe import ProbeAdapter


class NullExposureAdapter:
    """A no-op exposure adapter for early rollout slice development."""

    def adjust_exposure(
        self,
        *,
        deployment_id: str,
        target_weight: float,
        source_id: str | None = None,
        scope_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "deployment_id": deployment_id,
            "previous_weight": None,
            "target_weight": target_weight,
            "source_id": source_id,
            "scope_id": scope_id,
        }


class NullPromotionAdapter:
    """A no-op promotion adapter for early promotion slice development."""

    def promote(
        self,
        *,
        deployment_id: str,
        target_weight: float,
        source_id: str | None = None,
        scope_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "deployment_id": deployment_id,
            "target_weight": target_weight,
            "source_id": source_id,
            "scope_id": scope_id,
        }


class NullRegistryAdapter:
    """A no-op registry adapter for early vertical slice development."""

    def get_deployment_registry_entry(self, *, deployment_id: str) -> dict[str, Any]:
        return {
            "deployment_id": deployment_id,
            "registry_status": "registered",
            "version_hash": None,
            "serving_path_id": None,
        }


class NullRegulatoryAdapter:
    """A no-op regulatory adapter for early vertical slice development."""

    def verify_origin(self, *, origin_id: str) -> bool:
        return True


class NullProbeAdapter(ProbeAdapter):
    """A no-op probe adapter for early readiness slice development."""

    def execute(
        self,
        *,
        deployment_id: str,
        scope_id: str | None = None,
        source_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "healthy": True,
            "detail": {
                "latency_ms": 12,
                "scope_id": scope_id,
                "source_id": source_id,
            },
        }

    def resolve_source(self, *, source_id: str) -> dict[str, Any]:
        return {"source_id": source_id, "source_type": "null"}
