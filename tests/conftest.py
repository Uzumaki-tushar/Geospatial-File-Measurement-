"""
Shared Pytest fixtures.

- Ephemeral SQLite database per test run (in a temp dir).
- FastAPI TestClient wired to the test DB.
- Pre-generated sample files via make_samples.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import Base, get_db
from app.main import app

# Generate sample fixtures once per test session
@pytest.fixture(scope="session", autouse=True)
def generate_samples():
    """Generate sample fixture files before any tests run."""
    sample_dir = Path(__file__).parent.parent / "sample_data"
    sys.path.insert(0, str(sample_dir.parent))
    # Run the generator in-process
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_samples", sample_dir / "make_samples.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.make_kml(sample_dir / "sample.kml")
    mod.make_shapefile_zip(sample_dir / "sample_shapefile.zip")
    mod.make_3d_kml(sample_dir / "sample_3d.kml")
    mod.make_multizone_kml(sample_dir / "sample_multizone.kml")
    mod.make_missing_prj_zip(sample_dir / "sample_missing_prj.zip")
    mod.make_zipslip_zip(sample_dir / "sample_zipslip.zip")


@pytest.fixture()
def tmp_dirs(tmp_path):
    """Return (upload_dir, extract_dir) temp paths and patch settings."""
    upload = tmp_path / "uploads"
    extract = tmp_path / "extracted"
    upload.mkdir()
    extract.mkdir()
    return upload, extract


@pytest.fixture()
def test_client(tmp_dirs, tmp_path):
    """
    Return a FastAPI TestClient backed by an isolated in-memory SQLite database
    and temporary storage directories.
    """
    upload_dir, extract_dir = tmp_dirs
    db_path = tmp_path / "test.db"

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Patch settings and DB dependency
    from app.core import config

    config.settings.upload_dir = str(upload_dir)
    config.settings.extract_dir = str(extract_dir)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()
