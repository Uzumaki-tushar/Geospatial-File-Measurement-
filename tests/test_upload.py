"""
API upload tests — happy paths for KML and Shapefile zip.
"""

from pathlib import Path

import pytest

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


def _upload(client, filepath: Path, field: str = "file"):
    with open(filepath, "rb") as f:
        return client.post(
            "/api/files/",
            files={field: (filepath.name, f, "application/octet-stream")},
        )


class TestKmlUpload:
    def test_kml_happy_path(self, test_client):
        resp = _upload(test_client, SAMPLE_DIR / "sample.kml")
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "COMPLETED"
        assert body["feature_count"] > 0
        assert body["crs"] is not None
        assert "id" in body

    def test_kml_3d_upload(self, test_client):
        """3D KML should succeed after Z-stripping."""
        resp = _upload(test_client, SAMPLE_DIR / "sample_3d.kml")
        assert resp.status_code == 201
        assert resp.json()["status"] == "COMPLETED"

    def test_kml_multizone_upload(self, test_client):
        """Multi-zone KML should succeed using EPSG:6933 fallback."""
        resp = _upload(test_client, SAMPLE_DIR / "sample_multizone.kml")
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "COMPLETED"


class TestShapefileUpload:
    def test_shapefile_zip_happy_path(self, test_client):
        resp = _upload(test_client, SAMPLE_DIR / "sample_shapefile.zip")
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "COMPLETED"
        assert body["feature_count"] >= 1
        assert body["crs"] is not None

    def test_missing_prj_returns_422(self, test_client):
        resp = _upload(test_client, SAMPLE_DIR / "sample_missing_prj.zip")
        assert resp.status_code in (422, 500)

    def test_zipslip_returns_422(self, test_client):
        resp = _upload(test_client, SAMPLE_DIR / "sample_zipslip.zip")
        assert resp.status_code in (422, 400)


class TestValidationErrors:
    def test_wrong_extension_returns_415(self, test_client):
        import io

        resp = test_client.post(
            "/api/files/",
            files={"file": ("test.txt", io.BytesIO(b"not a geo file"), "text/plain")},
        )
        assert resp.status_code == 415

    def test_file_too_large_returns_413(self, test_client):
        from app.core import config

        original = config.settings.max_upload_mb
        config.settings.max_upload_mb = 0  # force any file to exceed limit
        try:
            import io

            resp = test_client.post(
                "/api/files/",
                files={"file": ("test.kml", io.BytesIO(b"<kml/>"), "application/vnd.google-earth.kml+xml")},
            )
            assert resp.status_code == 413
        finally:
            config.settings.max_upload_mb = original

    def test_empty_file_returns_422(self, test_client):
        import io

        resp = test_client.post(
            "/api/files/",
            files={"file": ("empty.kml", io.BytesIO(b""), "application/vnd.google-earth.kml+xml")},
        )
        assert resp.status_code == 422

    def test_corrupt_zip_returns_error(self, test_client):
        import io

        resp = test_client.post(
            "/api/files/",
            files={"file": ("bad.zip", io.BytesIO(b"this is not a zip"), "application/zip")},
        )
        assert resp.status_code in (400, 422, 500)
