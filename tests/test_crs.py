"""Unit tests for crs_service — zone derivation, multi-zone detection, transformers."""

import pytest

from app.services.crs_service import (
    get_utm_epsg,
    is_projected_metres,
    select_projected_crs,
    spans_multiple_utm_zones,
    EQUAL_AREA_EPSG,
)
from pyproj import CRS


class TestGetUtmEpsg:
    def test_northern_hemisphere(self):
        # Delhi (77.1°E, 28.7°N) → Zone 43N → EPSG:32643
        assert get_utm_epsg(77.1, 28.7) == "EPSG:32643"

    def test_southern_hemisphere(self):
        # Sydney (151.2°E, -33.9°N) → Zone 56S → EPSG:32756
        assert get_utm_epsg(151.2, -33.9) == "EPSG:32756"

    def test_zero_meridian(self):
        # London (0°, 51.5°N) → Zone 31N → EPSG:32631
        assert get_utm_epsg(0.0, 51.5) == "EPSG:32631"

    def test_near_zone_edge(self):
        # UTM zones are 6° wide starting at -180°.
        # Zone 43 covers 72°–78°E, zone 44 covers 78°–84°E.
        # 77.99° is still zone 43; 78.01° is zone 44.
        assert get_utm_epsg(77.99, 28.0) == "EPSG:32643"
        assert get_utm_epsg(78.01, 28.0) == "EPSG:32644"

    def test_negative_longitude(self):
        # New York (~74°W, 40.7°N) → Zone 18N → EPSG:32618
        assert get_utm_epsg(-74.0, 40.7) == "EPSG:32618"


class TestSpansMultipleUtmZones:
    def test_single_zone(self):
        # Within zone 43 (72°E–78°E)
        assert spans_multiple_utm_zones(72.0, 77.0) is False

    def test_crosses_zone_boundary(self):
        # Spans zones 43 and 44 (boundary at 78°E)
        assert spans_multiple_utm_zones(76.0, 80.0) is True

    def test_exact_boundary(self):
        # 78.0 → zone 44, 72.0 → zone 43 → multi-zone
        assert spans_multiple_utm_zones(72.0, 78.0) is True


class TestSelectProjectedCrs:
    def test_geographic_single_zone(self):
        # 77°E centroid → zone 43 (72°–78°E)
        crs = select_projected_crs("EPSG:4326", (74.0, 28.0, 77.0, 28.5))
        assert crs == "EPSG:32643"

    def test_geographic_multi_zone_uses_equal_area(self):
        # 10° wide spanning two UTM zones
        crs = select_projected_crs("EPSG:4326", (80.0, 20.0, 90.0, 25.0))
        assert crs == EQUAL_AREA_EPSG

    def test_projected_crs_returns_itself(self):
        # Already-projected CRS should pass through unchanged
        crs = select_projected_crs("EPSG:32643", (300000.0, 3100000.0, 310000.0, 3110000.0))
        assert crs == "EPSG:32643"


class TestIsProjectedMetres:
    def test_geographic_is_false(self):
        assert is_projected_metres(CRS.from_epsg(4326)) is False

    def test_utm_is_true(self):
        assert is_projected_metres(CRS.from_epsg(32643)) is True

    def test_equal_area_is_true(self):
        assert is_projected_metres(CRS.from_epsg(6933)) is True
