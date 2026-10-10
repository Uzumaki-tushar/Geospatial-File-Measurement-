"""File-handling utilities: safe storage, zip-slip detection, JSON sanitisation."""

import math
import os
import uuid
import zipfile
from pathlib import Path
from typing import Any

from app.core.exceptions import ZipSlipError


def generate_storage_path(upload_dir: str, extension: str) -> Path:
    """Return a unique, safe path under *upload_dir* with the given *extension*."""
    filename = f"{uuid.uuid4()}{extension}"
    return Path(upload_dir) / filename


def safe_extract_zip(zip_path: Path, extract_dir: Path) -> Path:
    """
    Extract *zip_path* into a unique sub-directory of *extract_dir*.

    Raises :class:`ZipSlipError` if any member's resolved path escapes the
    destination directory (zip-slip attack mitigation).

    Returns the path to the extraction sub-directory.
    """
    dest = extract_dir / str(uuid.uuid4())
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            member_path = dest / member.filename
            # Resolve and verify the path stays inside dest
            try:
                member_path.resolve().relative_to(dest.resolve())
            except ValueError:
                raise ZipSlipError()
            zf.extract(member, dest)

    return dest


def find_shapefile(extract_dir: Path) -> Path:
    """
    Recursively search *extract_dir* for a .shp file.

    Returns the first .shp found.  Raises :class:`FileNotFoundError` (builtin)
    if none is present — the caller translates this into an HTTP error.
    """
    shp_files = list(extract_dir.rglob("*.shp"))
    if not shp_files:
        raise FileNotFoundError("No .shp file found inside the uploaded zip archive.")
    return shp_files[0]


def validate_shapefile_sidecars(shp_path: Path) -> None:
    """
    Verify that the required sidecar files (.shx, .dbf, .prj) exist next to *shp_path*.

    Raises :class:`ValueError` with a descriptive message for each missing file.
    """
    stem = shp_path.stem
    parent = shp_path.parent
    missing = []
    for ext in (".shx", ".dbf", ".prj"):
        if not (parent / f"{stem}{ext}").exists():
            missing.append(ext)
    if missing:
        raise ValueError(
            f"Shapefile is missing required sidecar file(s): {', '.join(missing)}. "
            "Please include all of: .shp, .shx, .dbf, .prj inside the zip."
        )


def sanitise_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """
    Convert *properties* to a JSON-safe dictionary.

    - NaN / ±Inf  → None
    - pandas/numpy Timestamp → ISO-8601 string
    - numpy numeric scalars  → Python int / float
    """
    result: dict[str, Any] = {}
    for key, value in properties.items():
        result[key] = _sanitise_value(value)
    return result


def _sanitise_value(value: Any) -> Any:
    """Recursively sanitise a single value."""
    # numpy scalars — import lazily to avoid hard dependency at module level
    try:
        import numpy as np  # type: ignore[import]

        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            v = float(value)
            return None if (math.isnan(v) or math.isinf(v)) else v
        if isinstance(value, np.bool_):
            return bool(value)
    except ImportError:
        pass

    # pandas Timestamp
    try:
        import pandas as pd  # type: ignore[import]

        if isinstance(value, pd.Timestamp):
            return value.isoformat()
    except ImportError:
        pass

    # Plain Python float NaN / Inf
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None

    # Dicts and lists — recurse
    if isinstance(value, dict):
        return {k: _sanitise_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitise_value(v) for v in value]

    return value


def ensure_dirs(*paths: str) -> None:
    """Create directories if they do not already exist."""
    for p in paths:
        os.makedirs(p, exist_ok=True)
