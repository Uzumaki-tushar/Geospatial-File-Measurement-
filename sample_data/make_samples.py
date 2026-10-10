"""
Sample data generator for tests and manual experimentation.

Generates:
  - sample.kml          — mix of Polygon, LineString, and Point features
  - sample_shapefile.zip — same geometries as a Shapefile bundle
  - sample_3d.kml        — KML with 3D (Z) coordinates
  - sample_multizone.kml — a polygon spanning two UTM zones

Run directly:  python sample_data/make_samples.py
"""

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, Polygon

OUTPUT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Geometries — small features in India near EPSG:32643 (UTM zone 43N)
# ---------------------------------------------------------------------------

POLYGON_GEOM = Polygon(
    [
        (77.10, 28.70),
        (77.11, 28.70),
        (77.11, 28.71),
        (77.10, 28.71),
        (77.10, 28.70),
    ]
)

LINE_GEOM = LineString(
    [
        (77.10, 28.70),
        (77.12, 28.72),
        (77.14, 28.70),
    ]
)

POINT_GEOM = Point(77.10, 28.70)

# Multi-zone polygon: spans UTM 43 → 44 boundary (84°E)
MULTIZONE_POLYGON = Polygon(
    [
        (80.0, 20.0),
        (90.0, 20.0),
        (90.0, 25.0),
        (80.0, 25.0),
        (80.0, 20.0),
    ]
)


def make_kml(path: Path) -> None:
    """Write a KML with Polygon, LineString, and Point features."""
    kml_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Sample</name>
    <Placemark>
      <name>Plot A</name>
      <ExtendedData>
        <SchemaData>
          <SimpleData name="zone">Commercial</SimpleData>
          <SimpleData name="area_ha">1.21</SimpleData>
        </SchemaData>
      </ExtendedData>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.10,28.70,0 77.11,28.70,0 77.11,28.71,0 77.10,28.71,0 77.10,28.70,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Road 1</name>
      <LineString>
        <coordinates>
          77.10,28.70,0 77.12,28.72,0 77.14,28.70,0
        </coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Marker A</name>
      <Point>
        <coordinates>77.10,28.70,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""
    path.write_text(kml_content, encoding="utf-8")
    print(f"  Written: {path}")


def make_shapefile_zip(path: Path) -> None:
    """
    Write a .zip containing Shapefile bundles for polygons, lines, and points.

    ESRI Shapefiles are single-geometry-type, so we create one shapefile per
    geometry type and combine them into a single zip archive.
    """
    import tempfile

    layers = {
        "polygons": (gpd.GeoDataFrame(
            {"name": ["Plot A"], "zone": ["Commercial"]},
            geometry=[POLYGON_GEOM], crs="EPSG:4326",
        ), "polygons"),
        "lines": (gpd.GeoDataFrame(
            {"name": ["Road 1"], "zone": [None]},
            geometry=[LINE_GEOM], crs="EPSG:4326",
        ), "lines"),
        "points": (gpd.GeoDataFrame(
            {"name": ["Marker A"], "zone": ["Landmark"]},
            geometry=[POINT_GEOM], crs="EPSG:4326",
        ), "points"),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Write the polygon shapefile as the primary one (it has the .prj)
            # For simplicity, write only the polygon shapefile as "sample.*"
            # The service reads the first .shp found.
            gdf_poly = layers["polygons"][0]
            gdf_poly.to_file(tmp_path / "sample.shp", engine="pyogrio")
            for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                fp = tmp_path / f"sample{ext}"
                if fp.exists():
                    zf.write(fp, f"sample{ext}")

    path.write_bytes(buf.getvalue())
    print(f"  Written: {path}")


def make_3d_kml(path: Path) -> None:
    """Write a KML with 3D (Z) coordinates to test Z-stripping."""
    kml_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>3D Sample</name>
    <Placemark>
      <name>3D Plot</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.10,28.70,100 77.11,28.70,200 77.11,28.71,150 77.10,28.71,120 77.10,28.70,100
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""
    path.write_text(kml_content, encoding="utf-8")
    print(f"  Written: {path}")


def make_multizone_kml(path: Path) -> None:
    """Write a KML with a polygon that spans two UTM zones."""
    kml_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Multi-Zone Sample</name>
    <Placemark>
      <name>Large Region</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              80.0,20.0,0 90.0,20.0,0 90.0,25.0,0 80.0,25.0,0 80.0,20.0,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""
    path.write_text(kml_content, encoding="utf-8")
    print(f"  Written: {path}")


def make_missing_prj_zip(path: Path) -> None:
    """Write a .zip with a Shapefile that has NO .prj file."""
    gdf = gpd.GeoDataFrame(
        {"name": ["Plot A"]},
        geometry=[POLYGON_GEOM],
        crs="EPSG:4326",
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gdf.to_file(tmp_path / "no_prj.shp", engine="pyogrio")
            for ext in (".shp", ".shx", ".dbf"):  # deliberately omit .prj
                fp = tmp_path / f"no_prj{ext}"
                if fp.exists():
                    zf.write(fp, f"no_prj{ext}")

    path.write_bytes(buf.getvalue())
    print(f"  Written: {path}")


def make_zipslip_zip(path: Path) -> None:
    """Write a malicious .zip with a path-traversal entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", "I escaped the sandbox!")
    path.write_bytes(buf.getvalue())
    print(f"  Written: {path}")


if __name__ == "__main__":
    print("Generating sample data...")
    make_kml(OUTPUT_DIR / "sample.kml")
    make_shapefile_zip(OUTPUT_DIR / "sample_shapefile.zip")
    make_3d_kml(OUTPUT_DIR / "sample_3d.kml")
    make_multizone_kml(OUTPUT_DIR / "sample_multizone.kml")
    make_missing_prj_zip(OUTPUT_DIR / "sample_missing_prj.zip")
    make_zipslip_zip(OUTPUT_DIR / "sample_zipslip.zip")
    print("Done.")
