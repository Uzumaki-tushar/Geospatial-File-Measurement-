"""
CRS selection and transformer utilities.

All functions are pure (no side effects, no DB access).
Transformers are cached with lru_cache to avoid repeated PROJ lookups.
"""

import logging
import math
from functools import lru_cache

import pyproj
from pyproj import CRS, Transformer

logger = logging.getLogger(__name__)

# EPSG for the global equal-area fallback used when a feature spans >1 UTM zone
EQUAL_AREA_EPSG = "EPSG:6933"


def get_utm_epsg(lon: float, lat: float) -> str:
    """
    Derive the UTM EPSG code for a given *lon* / *lat* point.

    Zone number  = int((lon + 180) / 6) + 1
    Northern hemisphere → EPSG:326xx
    Southern hemisphere → EPSG:327xx
    """
    zone = int((lon + 180) / 6) + 1
    # Clamp zone to valid range [1, 60]
    zone = max(1, min(60, zone))
    hemisphere_offset = 32600 if lat >= 0 else 32700
    return f"EPSG:{hemisphere_offset + zone}"


def spans_multiple_utm_zones(minx: float, maxx: float) -> bool:
    """
    Return True if the longitude range *minx* → *maxx* crosses a UTM zone boundary.

    Each UTM zone covers 6° of longitude.
    """
    zone_min = int((minx + 180) / 6)
    zone_max = int((maxx + 180) / 6)
    return zone_max != zone_min


@lru_cache(maxsize=128)
def get_transformer(src_crs: str, dst_crs: str) -> Transformer:
    """
    Return a cached *pyproj.Transformer* from *src_crs* to *dst_crs*.

    ``always_xy=True`` ensures consistent (lon, lat) / (x, y) axis order
    regardless of the CRS authority definition.
    """
    return Transformer.from_crs(src_crs, dst_crs, always_xy=True)


def is_projected_metres(crs: CRS) -> bool:
    """Return True if *crs* is a projected CRS with linear units in metres."""
    if not crs.is_projected:
        return False
    axis_info = crs.axis_info
    if axis_info:
        unit = axis_info[0].unit_name.lower()
        return "metre" in unit or "meter" in unit
    return False


def select_projected_crs(
    src_crs_str: str,
    bounds: tuple[float, float, float, float],
) -> str:
    """
    Choose an appropriate projected CRS for measuring a geometry.

    Args:
        src_crs_str: Source CRS as an EPSG string (e.g. 'EPSG:4326').
        bounds:      (minx, miny, maxx, maxy) of the feature in source CRS units.

    Returns:
        EPSG string for the target projected CRS.

    Strategy:
        1. If source is already projected in metres → use it directly.
        2. If geographic → pick the UTM zone from the centroid.
        3. If the bounds span >1 UTM zone → use EPSG:6933 (equal-area).
    """
    src_crs = CRS.from_user_input(src_crs_str)

    if is_projected_metres(src_crs):
        return src_crs_str

    minx, miny, maxx, maxy = bounds
    centroid_lon = (minx + maxx) / 2.0
    centroid_lat = (miny + maxy) / 2.0

    # Check multi-zone span
    if spans_multiple_utm_zones(minx, maxx):
        logger.debug(
            "Feature spans multiple UTM zones (%.2f–%.2f lon); using %s",
            minx,
            maxx,
            EQUAL_AREA_EPSG,
        )
        return EQUAL_AREA_EPSG

    return get_utm_epsg(centroid_lon, centroid_lat)


def uses_geodesic_for_lines(
    src_crs_str: str,
    bounds: tuple[float, float, float, float],
) -> bool:
    """
    Return True when geodesic Geod calculation should be used for line length.

    This is the case when the source CRS is geographic AND the feature spans
    more than one UTM zone.
    """
    src_crs = CRS.from_user_input(src_crs_str)
    if is_projected_metres(src_crs):
        return False
    minx, _miny, maxx, _maxy = bounds
    return spans_multiple_utm_zones(minx, maxx)


def geodesic_length(geometry, src_crs_str: str) -> float:
    """
    Compute the geodesic length (metres) of a *LineString* or *MultiLineString*
    on the WGS-84 ellipsoid using :class:`pyproj.Geod`.

    Args:
        geometry:    Shapely geometry (LineString or MultiLineString).
        src_crs_str: Source CRS (used to convert lon/lat if not EPSG:4326).

    Returns:
        Total length in metres.
    """
    from shapely.geometry import MultiLineString

    geod = pyproj.Geod(ellps="WGS84")

    # Ensure we're working in geographic lon/lat
    src_crs = CRS.from_user_input(src_crs_str)
    if is_projected_metres(src_crs):
        # Re-project to geographic first
        transformer = get_transformer(src_crs_str, "EPSG:4326")
        from shapely.ops import transform

        geometry = transform(transformer.transform, geometry)

    total = 0.0
    lines = geometry.geoms if isinstance(geometry, MultiLineString) else [geometry]
    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            x0, y0 = coords[i][:2]
            x1, y1 = coords[i + 1][:2]
            _, _, dist = geod.inv(x0, y0, x1, y1)
            total += abs(dist)
    return total


def crs_display_string(crs: CRS) -> str:
    """Return a short human-readable identifier for a CRS (e.g. 'EPSG:4326')."""
    auth = crs.to_authority()
    if auth:
        return f"{auth[0]}:{auth[1]}"
    return crs.name or "Unknown"
