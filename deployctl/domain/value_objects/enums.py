"""Domain value-object enums."""

from __future__ import annotations

from enum import StrEnum

from deployctl.model.primitives import CheckResult, ProbeSource


class ExposureStage(StrEnum):
    NONE = "none"
    LIMITED = "limited"
    SCALED = "scaled"
    FULL = "full"
    RETRACTED = "retracted"


class CoherenceStatus(StrEnum):
    COHERENT = "coherent"
    NO_PLACED_VERSION = "no_placed_version"
    MISMATCH = "mismatch"
    INCOMPLETE = "incomplete"
    CONFLICTING = "conflicting"


class LedgerEntryType(StrEnum):
    INTENDED = "intended"
    PLACED = "placed"
    OBSERVED_RUNTIME = "observed_runtime"
    PREVIOUS_LIVE = "previous_live"
    PROMOTED_LIVE = "promoted_live"
    RESTORED_LIVE = "restored_live"


class ClaimKind(StrEnum):
    COVERAGE = "coverage"
    FUNCTIONAL = "functional"
    DEPENDENCY = "dependency"
    PERFORMANCE = "performance"
    SAFETY = "safety"
    OPERATIONAL = "operational"


class CheckResultStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    DEGRADED = "degraded"


__all__ = [
    "ExposureStage",
    "CoherenceStatus",
    "LedgerEntryType",
    "ClaimKind",
    "CheckResultStatus",
    "CheckResult",
    "ProbeSource",
]
