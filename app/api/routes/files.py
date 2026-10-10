"""
API route handlers for geospatial file upload and retrieval.

Route handlers are intentionally thin: all business logic lives in services.
"""

import json
import logging

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.file import (
    FeatureMeasurement,
    FileInfoResponse,
    FileUploadResponse,
    MeasurementDetail,
    MeasurementListResponse,
)
from app.services import file_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/", status_code=201, response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(..., description="A .kml file or a .zip containing a Shapefile"),
    db: Session = Depends(get_db),
):
    """
    Upload and process a geospatial file.

    Accepts a **.kml** or **.zip** (Shapefile) and returns file metadata
    including the detected CRS and feature count after processing.
    """
    content = await file.read()
    db_file = await file_service.upload_and_process(
        filename=file.filename or "upload",
        content=content,
        db=db,
    )
    return db_file


@router.get("/{file_id}/", response_model=FileInfoResponse)
def get_file(file_id: str, db: Session = Depends(get_db)):
    """
    Retrieve metadata for an uploaded file by its **id**.

    Returns the current processing status, detected CRS, and feature count.
    """
    db_file = file_service.get_file_info(file_id, db)
    return db_file


@router.get("/{file_id}/measurements/", response_model=MeasurementListResponse, response_model_by_alias=True)
def get_measurements(
    file_id: str,
    limit: int = Query(default=50, ge=1, le=500, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
):
    """
    Return paginated feature measurements for an uploaded file.

    The file must be in **COMPLETED** status; otherwise a 409 is returned.
    Each result item includes the geometry, properties, source CRS,
    measurement (area/length), the CRS used for calculation, and status.
    """
    db_file, features, total = file_service.get_measurements(file_id, db, limit, offset)

    results = []
    for feat in features:
        # Deserialise stored JSON strings
        geom = json.loads(feat.geometry)
        props = json.loads(feat.properties) if feat.properties else {}

        measurement = None
        if feat.measurement_type and feat.measurement_value is not None:
            measurement = MeasurementDetail(
                type=feat.measurement_type,
                value=feat.measurement_value,
                unit=feat.measurement_unit or "",
            )

        results.append(
            FeatureMeasurement(
                feature_index=feat.feature_index,
                geometry_type=feat.geometry_type,
                geometry=geom,
                properties=props,
                source_crs=db_file.crs,
                measurement=measurement,
                crs_used=feat.crs_used,
                measurement_status=feat.measurement_status,
                note=feat.note,
            )
        )

    return MeasurementListResponse(
        file_id=file_id,
        total=total,
        limit=limit,
        offset=offset,
        results=results,
    )
