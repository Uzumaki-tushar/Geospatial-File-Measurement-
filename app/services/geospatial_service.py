"""
Geospatial file reading service — pure I/O, no DB access.

Reads .kml (all layers via pyogrio) and .zip (Shapefile) and returns
a unified GeoDataFrame together with the detected CRS string.
"""

import logging
import zipfile
from pathlib import Path

import geopandas as gpd
import pyogrio

from app.core.exceptions import FileProcessingError
from app.utils.file_utils import (
    find_shapefile,
    safe_extract_zip,
    validate_shapefile_sidecars,
)

logger = logging.getLogger(__name__)


def read_kml(kml_path: Path, extract_dir: Path) -> gpd.GeoDataFrame:
    """
    Read all layers from a KML file and return a merged GeoDataFrame.

    Z coordinates are stripped to keep geometry 2-D.

    Args:
        kml_path:    Path to the .kml file on disk.
        extract_dir: Base extraction directory (unused for KML but kept for API symmetry).

    Returns:
        A GeoDataFrame with all features from all KML layers.

    Raises:
        :class:`FileProcessingError` on unreadable or empty KML.
    """
    try:
        layers = pyogrio.list_layers(kml_path)
    except Exception as exc:
        raise FileProcessingError(f"Cannot read KML file: {exc}") from exc

    if len(layers) == 0:
        raise FileProcessingError("KML file contains no layers.")

    frames: list[gpd.GeoDataFrame] = []
    for layer_name, _ in layers:
        try:
            gdf = gpd.read_file(kml_path, layer=layer_name, engine="pyogrio")
            frames.append(gdf)
            logger.debug("KML layer '%s': %d features", layer_name, len(gdf))
        except Exception as exc:
            logger.warning("Skipping KML layer '%s': %s", layer_name, exc)

    if not frames:
        raise FileProcessingError("No readable layers found in KML file.")

    merged = gpd.pd.concat(frames, ignore_index=True)
    gdf = gpd.GeoDataFrame(merged, crs=frames[0].crs)

    # KML is always EPSG:4326 — set explicitly if missing
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    # Drop Z coordinates
    gdf["geometry"] = gdf["geometry"].apply(_drop_z)

    return gdf


def read_shapefile_zip(zip_path: Path, extract_dir: Path) -> gpd.GeoDataFrame:
    """
    Safely extract a .zip archive and read the Shapefile within it.

    Args:
        zip_path:    Path to the uploaded .zip file.
        extract_dir: Base directory for extraction.

    Returns:
        A GeoDataFrame with all features from the Shapefile.

    Raises:
        :class:`FileProcessingError` on invalid archive, missing sidecars, or read errors.
    """
    # Validate it is actually a zip
    if not zipfile.is_zipfile(zip_path):
        raise FileProcessingError("The uploaded .zip file is corrupt or not a valid ZIP archive.")

    try:
        dest_dir = safe_extract_zip(zip_path, extract_dir)
    except Exception as exc:
        # ZipSlipError is already a GeoAPIError — re-raise as-is
        from app.core.exceptions import GeoAPIError

        if isinstance(exc, GeoAPIError):
            raise
        raise FileProcessingError(f"Failed to extract zip archive: {exc}") from exc

    try:
        shp_path = find_shapefile(dest_dir)
    except FileNotFoundError as exc:
        raise FileProcessingError(str(exc)) from exc

    try:
        validate_shapefile_sidecars(shp_path)
    except ValueError as exc:
        raise FileProcessingError(str(exc)) from exc

    try:
        gdf = gpd.read_file(shp_path, engine="pyogrio")
    except Exception as exc:
        raise FileProcessingError(f"Cannot read Shapefile: {exc}") from exc

    logger.debug("Shapefile '%s': %d features, CRS=%s", shp_path.name, len(gdf), gdf.crs)
    return gdf


def read_geospatial_file(
    file_path: Path,
    extract_dir: Path,
) -> tuple[gpd.GeoDataFrame, str]:
    """
    Dispatch to the correct reader based on file extension.

    Returns:
        (gdf, crs_string) tuple where *crs_string* is e.g. 'EPSG:4326'.

    Raises:
        :class:`FileProcessingError` if the file cannot be read or has no CRS.
    """
    ext = file_path.suffix.lower()

    if ext == ".kml":
        gdf = read_kml(file_path, extract_dir)
    elif ext == ".zip":
        gdf = read_shapefile_zip(file_path, extract_dir)
    else:
        raise FileProcessingError(f"Unsupported file extension: {ext}")

    # Validate CRS
    if gdf.crs is None:
        raise FileProcessingError(
            "Could not determine the coordinate reference system (CRS). "
            "For Shapefiles, ensure a valid .prj file is included."
        )

    # Validate non-empty
    if len(gdf) == 0:
        raise FileProcessingError("The uploaded file contains no features.")

    from app.services.crs_service import crs_display_string

    crs_str = crs_display_string(gdf.crs)
    logger.info("Read %d features with CRS=%s", len(gdf), crs_str)
    return gdf, crs_str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drop_z(geom):
    """Return a 2-D version of *geom* with Z coordinates removed."""
    if geom is None or geom.is_empty:
        return geom
    if not geom.has_z:
        return geom
    from shapely.ops import transform

    return transform(lambda x, y, *_z: (x, y), geom)
