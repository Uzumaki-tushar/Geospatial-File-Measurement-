"""
API validation tests — 404, 409, pagination, measurement structure.
"""

from pathlib import Path

import pytest

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


def _upload_kml(client):
    with open(SAMPLE_DIR / "sample.kml", "rb") as f:
        resp = client.post(
            "/api/files/",
            files={"file": ("sample.kml", f, "application/octet-stream")},
        )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestFileInfo:
    def test_get_file_info_returns_200(self, test_client):
        file_id = _upload_kml(test_client)
        resp = test_client.get(f"/api/files/{file_id}/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == file_id
        assert "created_at" in body

    def test_get_unknown_file_returns_404(self, test_client):
        resp = test_client.get("/api/files/does-not-exist/")
        assert resp.status_code == 404

    def test_error_field_present(self, test_client):
        file_id = _upload_kml(test_client)
        resp = test_client.get(f"/api/files/{file_id}/")
        assert "error_message" in resp.json()


class TestMeasurements:
    def test_measurements_returns_200(self, test_client):
        file_id = _upload_kml(test_client)
        resp = test_client.get(f"/api/files/{file_id}/measurements/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["file_id"] == file_id
        assert "total" in body
        assert "results" in body
        assert isinstance(body["results"], list)

    def test_measurements_unknown_file_returns_404(self, test_client):
        resp = test_client.get("/api/files/does-not-exist/measurements/")
        assert resp.status_code == 404

    def test_pagination(self, test_client):
        file_id = _upload_kml(test_client)
        resp1 = test_client.get(f"/api/files/{file_id}/measurements/?limit=1&offset=0")
        assert resp1.status_code == 200
        assert len(resp1.json()["results"]) == 1
        assert resp1.json()["limit"] == 1

        resp2 = test_client.get(f"/api/files/{file_id}/measurements/?limit=1&offset=1")
        assert resp2.status_code == 200

    def test_result_structure(self, test_client):
        file_id = _upload_kml(test_client)
        resp = test_client.get(f"/api/files/{file_id}/measurements/")
        results = resp.json()["results"]
        assert len(results) > 0
        first = results[0]
        assert "index" in first
        assert "geometry_type" in first
        assert "geometry" in first
        assert "properties" in first
        assert "status" in first
        assert "crs_used" in first

    def test_polygon_has_area_measurement(self, test_client):
        file_id = _upload_kml(test_client)
        resp = test_client.get(f"/api/files/{file_id}/measurements/")
        results = resp.json()["results"]
        polygon_results = [r for r in results if r["geometry_type"] == "Polygon"]
        assert len(polygon_results) > 0
        first_poly = polygon_results[0]
        assert first_poly["measurement"] is not None
        assert first_poly["measurement"]["type"] == "area"
        assert first_poly["measurement"]["unit"] == "m2"
        assert first_poly["measurement"]["value"] > 0

    def test_point_has_null_measurement(self, test_client):
        file_id = _upload_kml(test_client)
        resp = test_client.get(f"/api/files/{file_id}/measurements/")
        results = resp.json()["results"]
        point_results = [r for r in results if r["geometry_type"] == "Point"]
        if point_results:
            assert point_results[0]["measurement"] is None
            assert point_results[0]["status"] == "OK"


class TestHealth:
    def test_health_endpoint(self, test_client):
        resp = test_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
