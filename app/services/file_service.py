"""
File service — orchestrates the full upload-process-persist pipeline.

Responsibilities:
  1. Validate extension and size.
  2. Save file to disk under a UUID name.
  3. Create the DB record (PROCESSING).
  4. Delegate reading to geospatial_service.
  5. Delegate measurement to measurement_service.
  6. Bulk-insert feature rows.
  7. Update DB record (COMPLETED or FAILED).
"""

import json
import logging
from pathlib import Path

from shapely.geometry import mapping
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    FileTooLargeError,
    FileNotReadyError,
    UnsupportedFileTypeError,
)
from app.core.exceptions import FileNotFoundError as GeoFileNotFoundError
from app.core.exceptions import FileProcessingError, GeoAPIError
from app.db.models import FeatureModel, FileModel
from app.services import geospatial_service, measurement_service
from app.services.crs_service import crs_display_string
from app.utils.file_utils import ensure_dirs, generate_storage_path, sanitise_properties

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".kml", ".zip"}


# ---------------------------------------------------------------------------
# Upload & Process
# ---------------------------------------------------------------------------


async def upload_and_process(
    filename: str,
    content: bytes,
    db: Session,
) -> FileModel:
    """
    Validate, save, parse, measure, and persist a geospatial file.

    Args:
        filename: Original filename from the multipart upload.
        content:  Raw file bytes.
        db:       Active SQLAlchemy session.

    Returns:
        The persisted :class:`FileModel` with status COMPLETED.

    Raises:
        :class:`GeoAPIError` subclasses for all expected failures.
    """
    # --- 1. Validate extension ---
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(ext or "<no extension>")

    # --- 2. Validate size ---
    if len(content) > settings.max_upload_bytes:
        raise FileTooLargeError(settings.max_upload_mb)

    if len(content) == 0:
        raise FileProcessingError("Uploaded file is empty.")

    # --- 3. Ensure storage directories exist ---
    ensure_dirs(settings.upload_dir, settings.extract_dir)

    # --- 4. Save to disk ---
    stored_path = generate_storage_path(settings.upload_dir, ext)
    stored_path.write_bytes(content)
    logger.info("Saved upload to %s (%d bytes)", stored_path, len(content))

    # --- 5. Create DB record ---
    db_file = FileModel(
        filename=filename,
        stored_path=str(stored_path),
        status="PROCESSING",
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    # --- 6. Process the file ---
    try:
        _process_file(db_file, stored_path, db)
    except GeoAPIError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error processing file %s", db_file.id)
        db_file.status = "FAILED"
        db_file.error_message = f"Unexpected processing error: {exc}"
        db.commit()
        raise FileProcessingError(f"File processing failed: {exc}") from exc

    return db_file


def _process_file(db_file: FileModel, stored_path: Path, db: Session) -> None:
    """Inner processing — wrapped so failures can set status=FAILED cleanly."""
    extract_dir = Path(settings.extract_dir)

    try:
        gdf, crs_str = geospatial_service.read_geospatial_file(stored_path, extract_dir)
    except GeoAPIError as exc:
        db_file.status = "FAILED"
        db_file.error_message = exc.message
        db.commit()
        raise

    # Determine CRS string for the source
    source_crs = crs_str

    feature_rows: list[FeatureModel] = []

    for idx, row in gdf.iterrows():
        geom = row.geometry
        properties_raw = {
            col: row[col]
            for col in gdf.columns
            if col != "geometry" and col != gdf.geometry.name
        }
        properties = sanitise_properties(properties_raw)

        # Build GeoJSON dict for the geometry
        if geom is None or geom.is_empty:
            geom_dict = {"type": "Point", "coordinates": []}
            geom_type = "Unknown"
        else:
            geom_dict = mapping(geom)
            geom_type = geom.geom_type

        # Measure
        result = measurement_service.measure_feature(
            geom_dict=dict(geom_dict),
            src_crs_str=source_crs,
        )

        feature_rows.append(
            FeatureModel(
                file_id=db_file.id,
                feature_index=int(idx),
                geometry_type=geom_type,
                geometry=json.dumps(geom_dict),
                properties=json.dumps(properties),
                measurement_type=result.measurement_type,
                measurement_value=result.measurement_value,
                measurement_unit=result.measurement_unit,
                crs_used=result.crs_used,
                measurement_status=result.status,
                note=result.note,
            )
        )

    # Bulk insert
    db.bulk_save_objects(feature_rows)

    db_file.status = "COMPLETED"
    db_file.crs = source_crs
    db_file.feature_count = len(feature_rows)
    db.commit()
    db.refresh(db_file)
    logger.info(
        "File %s processed: %d features, CRS=%s", db_file.id, db_file.feature_count, source_crs
    )


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def get_file_info(file_id: str, db: Session) -> FileModel:
    """
    Fetch a :class:`FileModel` by *file_id*.

    Raises :class:`GeoFileNotFoundError` if not found.
    """
    db_file = db.get(FileModel, file_id)
    if db_file is None:
        raise GeoFileNotFoundError(file_id)
    return db_file


def get_measurements(
    file_id: str,
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> tuple[FileModel, list[FeatureModel], int]:
    """
    Return paginated feature measurements for *file_id*.

    Args:
        file_id: UUID of the file.
        db:      Active DB session.
        limit:   Page size.
        offset:  Page offset.

    Returns:
        (file_model, features_page, total_count) tuple.

    Raises:
        :class:`GeoFileNotFoundError` if the file does not exist.
        :class:`FileNotReadyError` if the file is not COMPLETED.
    """
    db_file = get_file_info(file_id, db)

    if db_file.status != "COMPLETED":
        raise FileNotReadyError(file_id, db_file.status)

    from sqlalchemy import func, select

    total: int = db.scalar(
        select(func.count()).where(FeatureModel.file_id == file_id)
    )
    features = (
        db.execute(
            select(FeatureModel)
            .where(FeatureModel.file_id == file_id)
            .order_by(FeatureModel.feature_index)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return db_file, list(features), total
