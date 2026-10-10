"""
Measurement service — pure functions, no DB access.

Computes area (m²) for Polygon/MultiPolygon and length (m) for
LineString/MultiLineString after projecting to an appropriate CRS.
"""

import logging
from dataclasses import dataclass
from typing import Any

from pyproj import CRS
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import transform

from app.services import crs_service

logger = logging.getLogger(__name__)

# Geometry types that support measurements
POLYGON_TYPES = {"Polygon", "MultiPolygon"}
LINESTRING_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}


@dataclass
class MeasurementResult:
    """Holds the outcome of measuring a single feature."""

    measurement_type: str | None  # "area" | "length" | None
    measurement_value: float | None
    measurement_unit: str | None  # "m2" | "m" | None
    crs_used: str | None
    status: str  # OK | SKIPPED | UNSUPPORTED | ERROR
    note: str | None
    repaired: bool = False


def measure_feature(
    geom_dict: dict[str, Any],
    src_crs_str: str,
) -> MeasurementResult:
    """
    Measure a single feature geometry.

    Args:
        geom_dict:   GeoJSON geometry dict (e.g. from shapely.mapping()).
        src_crs_str: EPSG string for the source CRS.

    Returns:
        :class:`MeasurementResult` with all relevant fields filled in.
    """
    # Reconstruct Shapely geometry
    try:
        geom = shape(geom_dict)
    except Exception as exc:
        logger.warning("Cannot parse geometry: %s", exc)
        return MeasurementResult(
            measurement_type=None,
            measurement_value=None,
            measurement_unit=None,
            crs_used=None,
            status="ERROR",
            note=f"Could not parse geometry: {exc}",
        )

    # Empty geometry
    if geom is None or geom.is_empty:
        return MeasurementResult(
            measurement_type=None,
            measurement_value=None,
            measurement_unit=None,
            crs_used=None,
            status="SKIPPED",
            note="Empty geometry — skipped.",
        )

    # Repair invalid geometry
    note: str | None = None
    repaired = False
    if not geom.is_valid:
        geom = make_valid(geom)
        note = "Geometry was invalid and has been repaired with shapely.make_valid."
        repaired = True
        logger.debug("Repaired invalid geometry.")

    geom_type = geom.geom_type

    # Points — no measurement required
    if geom_type in POINT_TYPES:
        return MeasurementResult(
            measurement_type=None,
            measurement_value=None,
            measurement_unit=None,
            crs_used=None,
            status="OK",
            note="No measurement for point geometries.",
            repaired=repaired,
        )

    # Unsupported types (GeometryCollection, etc.)
    if geom_type not in POLYGON_TYPES and geom_type not in LINESTRING_TYPES:
        return MeasurementResult(
            measurement_type=None,
            measurement_value=None,
            measurement_unit=None,
            crs_used=None,
            status="UNSUPPORTED",
            note=f"Geometry type '{geom_type}' is not supported for measurement.",
            repaired=repaired,
        )

    # Strip Z coordinates to avoid PROJ dimension mismatch
    if geom.has_z:
        geom = _strip_z(geom)

    bounds = geom.bounds  # (minx, miny, maxx, maxy)

    # --- LineString: check for geodesic path first ---
    if geom_type in LINESTRING_TYPES:
        src_crs_obj = CRS.from_user_input(src_crs_str)
        if crs_service.uses_geodesic_for_lines(src_crs_str, bounds):
            try:
                length_m = crs_service.geodesic_length(geom, src_crs_str)
                return MeasurementResult(
                    measurement_type="length",
                    measurement_value=round(length_m, 4),
                    measurement_unit="m",
                    crs_used="Geodesic(WGS84)",
                    status="OK",
                    note=_join_notes(
                        note, "Length computed geodesically (feature spans multiple UTM zones)."
                    ),
                    repaired=repaired,
                )
            except Exception as exc:
                logger.exception("Geodesic length failed: %s", exc)
                return MeasurementResult(
                    measurement_type=None,
                    measurement_value=None,
                    measurement_unit=None,
                    crs_used=None,
                    status="ERROR",
                    note=f"Geodesic length calculation failed: {exc}",
                )

    # --- Select projected CRS ---
    try:
        target_crs_str = crs_service.select_projected_crs(src_crs_str, bounds)
    except Exception as exc:
        logger.exception("CRS selection failed: %s", exc)
        return MeasurementResult(
            measurement_type=None,
            measurement_value=None,
            measurement_unit=None,
            crs_used=None,
            status="ERROR",
            note=f"CRS selection failed: {exc}",
        )

    # --- Transform geometry ---
    try:
        transformer = crs_service.get_transformer(src_crs_str, target_crs_str)
        projected_geom = transform(transformer.transform, geom)
    except Exception as exc:
        logger.exception("Geometry transform failed: %s", exc)
        return MeasurementResult(
            measurement_type=None,
            measurement_value=None,
            measurement_unit=None,
            crs_used=target_crs_str,
            status="ERROR",
            note=f"Projection failed: {exc}",
        )

    # --- Measure ---
    try:
        if geom_type in POLYGON_TYPES:
            value = projected_geom.area
            return MeasurementResult(
                measurement_type="area",
                measurement_value=round(value, 4),
                measurement_unit="m2",
                crs_used=target_crs_str,
                status="OK",
                note=note,
                repaired=repaired,
            )
        else:  # LineString / MultiLineString
            value = projected_geom.length
            return MeasurementResult(
                measurement_type="length",
                measurement_value=round(value, 4),
                measurement_unit="m",
                crs_used=target_crs_str,
                status="OK",
                note=note,
                repaired=repaired,
            )
    except Exception as exc:
        logger.exception("Measurement failed: %s", exc)
        return MeasurementResult(
            measurement_type=None,
            measurement_value=None,
            measurement_unit=None,
            crs_used=target_crs_str,
            status="ERROR",
            note=f"Measurement failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_z(geom):
    """Return a 2-D copy of *geom* with Z coordinates removed."""
    from shapely.ops import transform as _transform

    return _transform(lambda x, y, *_z: (x, y), geom)


def _join_notes(*parts: str | None) -> str | None:
    """Concatenate non-None note strings separated by a space."""
    joined = " ".join(p for p in parts if p)
    return joined if joined else None
