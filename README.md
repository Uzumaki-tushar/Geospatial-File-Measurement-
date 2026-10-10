# Geospatial File Measurement API

A production-quality FastAPI backend service that accepts `.kml` or `.zip` (Shapefile) geospatial files, extracts every vector feature, computes accurate spatial measurements (area for polygons, length for lines) using a correctly projected CRS, and exposes the results through a clean REST API.

---

## Table of Contents

1. [Setup (Local)](#setup-local)
2. [Setup (Docker)](#setup-docker)
3. [API Reference](#api-reference)
4. [Architecture](#architecture)
5. [Design Decisions](#design-decisions)
6. [Testing](#testing)
7. [Learnings](#learnings)
8. [Future Scope](#future-scope)

---

## Setup (Local)

### Prerequisites

- Python 3.11+
- `git`

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/geospatial-measurement-api.git
cd geospatial-measurement-api

# 2. Create a virtual environment and install dependencies
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# 3. Configure the environment
cp .env.example .env
# Edit .env if needed (defaults are fine for local development)

# 4. Generate sample test files (optional)
python sample_data/make_samples.py

# 5. Start the development server
uvicorn app.main:app --reload
```

The API is now running at **http://localhost:8000**.
Interactive Swagger docs are available at **http://localhost:8000/docs**.

---

## Setup (Docker)

```bash
# Build the image
docker build -t geospatial-api .

# Run the container
docker run -p 8000:8000 \
  -e MAX_UPLOAD_MB=50 \
  -e DATABASE_URL=sqlite:///./geospatial.db \
  geospatial-api
```

The API is available at **http://localhost:8000**.

---

## API Reference

### `POST /api/files/`

Upload and process a `.kml` or `.zip` geospatial file.

**Request** (multipart/form-data):

```bash
curl -X POST http://localhost:8000/api/files/ \
  -F "file=@sample_data/sample.kml"
```

**Success response (201)**:

```json
{
  "id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

**Error responses**:

| Status | Cause |
|--------|-------|
| 413 | File exceeds MAX_UPLOAD_MB |
| 415 | Not a .kml or .zip file |
| 422 | Missing .prj / no features / zip-slip / empty file |
| 400 | Corrupt zip archive |

---

### `GET /api/files/{id}/`

Retrieve metadata for an uploaded file.

```bash
curl http://localhost:8000/api/files/c9bf9e57-1685-4c89-bafb-ff5af830be8a/
```

**Response (200)**:

```json
{
  "id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error_message": null,
  "created_at": "2026-10-09T00:40:00Z"
}
```

---

### `GET /api/files/{id}/measurements/?limit=50&offset=0`

Return paginated feature measurements.

```bash
curl "http://localhost:8000/api/files/c9bf9e57.../measurements/?limit=10&offset=0"
```

**Response (200)**:

```json
{
  "file_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "total": 3,
  "limit": 10,
  "offset": 0,
  "results": [
    {
      "index": 0,
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[77.10, 28.70], [77.11, 28.70], [77.11, 28.71], [77.10, 28.71], [77.10, 28.70]]]
      },
      "properties": { "name": "Plot A", "zone": "Commercial" },
      "source_crs": "EPSG:4326",
      "measurement": { "type": "area", "value": 1073842.25, "unit": "m2" },
      "crs_used": "EPSG:32643",
      "status": "OK",
      "note": null
    },
    {
      "index": 1,
      "geometry_type": "LineString",
      "geometry": { "type": "LineString", "coordinates": [[77.10, 28.70], [77.12, 28.72], [77.14, 28.70]] },
      "properties": { "name": "Road 1" },
      "source_crs": "EPSG:4326",
      "measurement": { "type": "length", "value": 4342.18, "unit": "m" },
      "crs_used": "EPSG:32643",
      "status": "OK",
      "note": null
    },
    {
      "index": 2,
      "geometry_type": "Point",
      "geometry": { "type": "Point", "coordinates": [77.10, 28.70] },
      "properties": { "name": "Marker A" },
      "source_crs": "EPSG:4326",
      "measurement": null,
      "crs_used": null,
      "status": "OK",
      "note": "No measurement for point geometries."
    }
  ]
}
```

**Error responses**:

| Status | Cause |
|--------|-------|
| 404 | Unknown file ID |
| 409 | File not in COMPLETED state |

---

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status": "healthy", "version": "1.0.0"}
```

---

## Architecture

### Project Structure

```
app/
├── main.py                      # FastAPI app, lifespan, middleware
├── api/routes/files.py          # Thin HTTP route handlers
├── core/
│   ├── config.py                # pydantic-settings configuration
│   └── exceptions.py           # Custom exceptions + global handlers
├── db/
│   ├── database.py              # SQLAlchemy engine, session, WAL mode
│   └── models.py                # ORM models: FileModel, FeatureModel
├── schemas/file.py              # Pydantic v2 request/response schemas
├── services/
│   ├── file_service.py          # Orchestrator (validate, store, process, persist)
│   ├── geospatial_service.py    # Pure file I/O (KML + safe Shapefile unpack)
│   ├── crs_service.py           # Pure CRS selection + transformer cache
│   └── measurement_service.py  # Pure geometry measurements + repair
└── utils/file_utils.py          # Storage, zip-slip guard, JSON sanitisation
```

### File Processing Flow

```
POST /api/files/
  ├── Validate: extension ∈ {.kml, .zip}, size ≤ MAX_UPLOAD_MB, non-empty
  ├── Save: storage/uploads/<uuid>.<ext>  (user filename never touches disk)
  ├── DB insert: status = PROCESSING
  ├── Dispatch:
  │     .kml  → pyogrio.list_layers → read all layers → merge GeoDataFrame → strip Z
  │     .zip  → safe_extract_zip (zip-slip guard) → find .shp → validate sidecars → read
  ├── Validate GeoDataFrame: CRS present, features > 0
  ├── For each feature:
  │     ├── Sanitise properties (NaN → null, Timestamp → ISO, numpy → Python)
  │     ├── Detect geometry state (empty / invalid / valid)
  │     │     invalid → shapely.make_valid → note added
  │     │     empty   → status=SKIPPED
  │     └── Measure (see below)
  ├── Bulk insert FeatureModel rows
  └── DB update: status = COMPLETED, crs, feature_count
```

### Measurement Calculation Flow

```
measure_feature(geom_dict, src_crs_str)
  ├── Point / MultiPoint  → measurement=null, status=OK
  ├── GeometryCollection  → status=UNSUPPORTED
  ├── Empty geometry      → status=SKIPPED
  ├── Invalid geometry    → shapely.make_valid → continue
  └── Polygon / MultiPolygon / LineString / MultiLineString:
        ├── Strip Z coordinates
        ├── select_projected_crs(src_crs, bounds):
        │     ├── Already projected (metres) → use directly
        │     ├── Geographic + single UTM zone → EPSG:326xx / 327xx
        │     └── Geographic + multi-zone     → EPSG:6933 (area) / Geod (length)
        ├── Transformer.from_crs(src, tgt, always_xy=True)  [LRU cached]
        ├── shapely.ops.transform → projected geometry
        └── .area (m²) or .length (m) → MeasurementResult
```

### CRS Handling

Geographic coordinates (EPSG:4326, degrees of longitude/latitude) cannot be used directly for area or distance calculations because:
- A degree of longitude has different physical lengths at different latitudes.
- `polygon.area` on degree-coordinates returns a dimensionless number in degrees², not m².

**Strategy**:
1. **Already-projected**: If the source CRS is already in metres (e.g., EPSG:32643), measure directly.
2. **UTM Zone**: Derive the optimal UTM zone from the feature centroid:
   `zone = int((lon + 180) / 6) + 1`. North → EPSG:326xx, South → EPSG:327xx.
3. **Multi-zone fallback**: If `bounds.maxx - bounds.minx > 6°` (spans multiple UTM zones):
   - Polygons → project to EPSG:6933 (Cylindrical Equal-Area, global equal-area)
   - Lines → `pyproj.Geod(ellps='WGS84').inv()` geodesic length
4. **Transformer caching**: `Transformer.from_crs` results are memoised via `@lru_cache(maxsize=128)`.

---

## Design Decisions

### UTM vs. Equal-Area vs. Geodesic
- **UTM** was chosen as the primary local projection because it is conformal (preserves angles/shape), widely understood, and has < 0.1% scale distortion within a zone. Ideal for cadastral/survey data.
- **EPSG:6933** (Equal-Area Cylindrical) is used when a polygon spans multiple UTM zones. Scale distortion across zones would produce large errors; equal-area projections preserve surface area globally.
- **Geodesic (pyproj.Geod)** is used for multi-zone line lengths. It computes distances directly on the WGS-84 ellipsoid without any projection, which is the most accurate method for long routes.

### Synchronous Processing vs. Background Jobs
Processing is performed synchronously in the upload request. This keeps the architecture simple (no Celery/Redis required) and is acceptable for files up to 50 MB. For production with large files or concurrent users, a background task queue (Celery + RQ) is the recommended next step.

### SQLite vs. PostGIS
SQLite was chosen for zero-setup local evaluation. The SQLAlchemy abstraction makes switching to PostgreSQL/PostGIS trivial — just change `DATABASE_URL`. PostGIS would unlock spatial indexing and native geometry queries.

### pyogrio vs. fiona
`pyogrio` was chosen because it provides pre-compiled binary wheels that bundle GDAL — no system-level GDAL installation is required. It is also significantly faster than `fiona` for reading large files.

### Missing `.prj` Policy
A Shapefile without a `.prj` file cannot have its CRS determined unambiguously. Rather than defaulting to EPSG:4326 (which would silently produce wrong results if the assumption is incorrect), the service rejects the upload with HTTP 422 and a clear message asking the user to include the `.prj` file.

---

## Testing

```bash
# Run the full test suite
pytest -v

# Run with coverage (optional)
pip install pytest-cov
pytest --cov=app --cov-report=term-missing
```

### Test Coverage

| Module | Tests |
|--------|-------|
| `crs_service` | UTM zones (north/south/edge), multi-zone detection, projection selection |
| `measurement_service` | Area accuracy (0.5% vs Geod), length accuracy, MultiPolygon, points, empty, invalid, unsupported |
| `test_upload` | KML happy path, 3D KML, multi-zone KML, shapefile zip, missing .prj, zip-slip, wrong extension, too large, empty, corrupt zip |
| `test_validation` | 404, pagination, response structure, polygon has area, point has null measurement, health endpoint |

---

## Learnings

1. **Coordinate order matters**: PROJ CRS definitions often use (latitude, longitude) axis order, which is the opposite of GIS software conventions. Using `always_xy=True` on every transformer prevents silent axis-flip bugs.
2. **Z coordinates break 2D projections**: KML commonly embeds altitude (Z). PROJ transformers for 2D UTM projections reject 3D input. Explicitly stripping Z before any transform prevents cryptic GEOS errors.
3. **Shapely 2.0 make_valid returns typed geometry**: The result of `make_valid` on a self-intersecting polygon can be a MultiPolygon or a GeometryCollection, not always a Polygon. Downstream code must handle the new geometry type.
4. **pyogrio multi-layer KML**: KML files can have multiple folders (layers). A naive `gpd.read_file(kml)` only reads the first layer. Using `pyogrio.list_layers` + per-layer reads ensures all features are captured.
5. **JSON safety in pandas**: GeoPandas DataFrames routinely contain NumPy scalar types (`float64`, `int64`), `NaT`, and `Timestamp`. These are not JSON-serialisable by default. A dedicated sanitiser is essential.

---

## Future Scope

- **Background processing** (Celery + Redis / RQ): Decouple file processing from the HTTP request lifecycle for large files and concurrent users.
- **PostGIS backend**: Replace SQLite with PostgreSQL + PostGIS for spatial indexing, efficient bounding-box queries, and native geometry storage.
- **Additional formats**: GeoJSON, GeoPackage (GPKG), FlatGeobuf, DXF support via pyogrio.
- **CRS override parameter**: Allow clients to pass a `?crs=EPSG:32643` query param to override automatic CRS detection.
- **Authentication & authorisation**: API key / OAuth2 for multi-tenant deployments.
- **Large-file streaming**: Stream uploads using `multipart` chunked reading instead of buffering entire files in memory.
- **Map preview**: Generate a static PNG map thumbnail (using `matplotlib` + `contextily`) for each uploaded file.
- **Alembic migrations**: Replace `create_all` with Alembic for production-grade schema versioning.
- **Antimeridian handling**: Geometries crossing the 180°/-180° meridian require special splitting before projection. Currently documented as a known limitation.
- **OpenTelemetry tracing**: Add distributed tracing for production observability.
#   G e o s p a t i a l - F i l e - M e a s u r e m e n t -  
 