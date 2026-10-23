"""Exposure request/response schemas.

These schemas mirror the shape exposed by ExposureController.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ExposureAction(str):
    begin_limited: str = "begin_limited"
    increase_slice: str = "increase_slice"
    full_exposure: str = "full_exposure"
    retract: str = "retract"


class ExposureRequest(BaseModel):
    action: str
    route_id: str | None = None
    slice_params: dict[str, Any] | None = None


class ExposureResponse(BaseModel):
    deployment_id: str
    action: str
    successful: bool
    current_status: str
    error: str | None = None
    adapter_output: dict[str, Any] | None = None


exposure = ExposureResponse
