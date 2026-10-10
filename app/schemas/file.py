"""Pydantic v2 request and response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# File schemas
# ---------------------------------------------------------------------------


class FileUploadResponse(BaseModel):
    """Response body returned after a successful upload (POST /api/files/)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: str


class FileInfoResponse(BaseModel):
    """Full file metadata returned by GET /api/files/{id}/."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: str
    error_message: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Measurement schemas
# ---------------------------------------------------------------------------


class MeasurementDetail(BaseModel):
    """Measurement result for a single feature."""

    type: str  # "area" or "length"
    value: float
    unit: str  # "m2" or "m"


class FeatureMeasurement(BaseModel):
    """Single feature item returned inside the measurements list."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    index: int = Field(alias="feature_index")
    geometry_type: str
    geometry: Any  # parsed GeoJSON dict
    properties: Any  # parsed JSON dict
    source_crs: str | None = None
    measurement: MeasurementDetail | None = None
    crs_used: str | None = None
    status: str = Field(alias="measurement_status")
    note: str | None = None


class MeasurementListResponse(BaseModel):
    """Paginated response from GET /api/files/{id}/measurements/."""

    file_id: str
    total: int
    limit: int
    offset: int
    results: list[FeatureMeasurement]


# ---------------------------------------------------------------------------
# Health schema
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
