"""
Unit tests for measurement_service.

Key assertions:
  - A 0.01° square near the equator ≈ 1.23 km² (within 0.5% of Geod reference).
  - MultiPolygon area = sum of parts.
  - Points return None measurement with status OK.
  - GeometryCollection → UNSUPPORTED.
  - Empty geometry → SKIPPED.
  - Invalid (self-intersecting) polygon → repaired + area computed.
  - LineString length within 0.5% of geodesic reference.
"""

import math

import pyproj
import pytest
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
    mapping,
)

from app.services.measurement_service import measure_feature

GEOD = pyproj.Geod(ellps="WGS84")
SRC_CRS = "EPSG:4326"
TOLERANCE = 0.005  # 0.5%


def _geom(shapely_geom) -> dict:
    return dict(mapping(shapely_geom))


def _geodesic_area(polygon: Polygon) -> float:
    """Compute geodesic area via pyproj.Geod as a reference value."""
    lons, lats = zip(*list(polygon.exterior.coords))
    area, _ = GEOD.polygon_area_perimeter(lons, lats)
    return abs(area)


def _geodesic_length(line: LineString) -> float:
    """Compute geodesic length via pyproj.Geod as a reference value."""
    coords = list(line.coords)
    total = 0.0
    for i in range(len(coords) - 1):
        _, _, dist = GEOD.inv(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        total += abs(dist)
    return total


# ── Polygon ──────────────────────────────────────────────────────────────────

class TestPolygonMeasurement:
    # 0.01° square near equator
    SQUARE = Polygon(
        [(0.0, 0.0), (0.01, 0.0), (0.01, 0.01), (0.0, 0.01), (0.0, 0.0)]
    )
    # ≈ 1.23 km² at equator
    EXPECTED_AREA_M2 = 1_230_000  # rough lower bound

    def test_polygon_area_approximate(self):
        result = measure_feature(_geom(self.SQUARE), SRC_CRS)
        assert result.status == "OK"
        assert result.measurement_type == "area"
        assert result.measurement_unit == "m2"
        assert result.measurement_value is not None
        # Sanity: should be roughly 1.2 km² (1,200,000 m²)
        assert 1_100_000 < result.measurement_value < 1_400_000

    def test_polygon_area_within_tolerance_of_geodesic(self):
        ref = _geodesic_area(self.SQUARE)
        result = measure_feature(_geom(self.SQUARE), SRC_CRS)
        assert result.measurement_value is not None
        diff = abs(result.measurement_value - ref) / ref
        assert diff < TOLERANCE, f"Area differs from geodesic by {diff:.2%} (> 0.5%)"

    def test_multipolygon_area_equals_sum(self):
        p1 = Polygon([(0.0, 0.0), (0.01, 0.0), (0.01, 0.01), (0.0, 0.01), (0.0, 0.0)])
        p2 = Polygon(
            [(0.02, 0.0), (0.03, 0.0), (0.03, 0.01), (0.02, 0.01), (0.02, 0.0)]
        )
        mp = MultiPolygon([p1, p2])
        result = measure_feature(_geom(mp), SRC_CRS)
        r1 = measure_feature(_geom(p1), SRC_CRS)
        r2 = measure_feature(_geom(p2), SRC_CRS)
        assert result.status == "OK"
        combined = r1.measurement_value + r2.measurement_value
        assert abs(result.measurement_value - combined) / combined < 0.01


# ── LineString ────────────────────────────────────────────────────────────────

class TestLineStringMeasurement:
    LINE = LineString([(77.10, 28.70), (77.12, 28.72)])

    def test_linestring_length(self):
        result = measure_feature(_geom(self.LINE), SRC_CRS)
        assert result.status == "OK"
        assert result.measurement_type == "length"
        assert result.measurement_unit == "m"
        assert result.measurement_value is not None and result.measurement_value > 0

    def test_linestring_within_tolerance_of_geodesic(self):
        ref = _geodesic_length(self.LINE)
        result = measure_feature(_geom(self.LINE), SRC_CRS)
        diff = abs(result.measurement_value - ref) / ref
        assert diff < TOLERANCE, f"Length differs from geodesic by {diff:.2%}"


# ── Point ─────────────────────────────────────────────────────────────────────

class TestPointMeasurement:
    def test_point_returns_none_measurement(self):
        result = measure_feature(_geom(Point(77.1, 28.7)), SRC_CRS)
        assert result.status == "OK"
        assert result.measurement_type is None
        assert result.measurement_value is None

    def test_note_mentions_points(self):
        result = measure_feature(_geom(Point(77.1, 28.7)), SRC_CRS)
        assert result.note is not None and "point" in result.note.lower()


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_geometry_is_skipped(self):
        empty = Polygon()
        result = measure_feature(_geom(empty), SRC_CRS)
        assert result.status == "SKIPPED"
        assert result.measurement_value is None

    def test_geometry_collection_is_unsupported(self):
        gc = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
        result = measure_feature(_geom(gc), SRC_CRS)
        assert result.status == "UNSUPPORTED"

    def test_invalid_polygon_is_repaired(self):
        # Bowtie (self-intersecting) polygon
        bow = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
        assert not bow.is_valid  # confirm it really is invalid
        result = measure_feature(_geom(bow), SRC_CRS)
        assert result.status == "OK"
        assert result.measurement_value is not None
        assert result.repaired is True
