"""Exercise the public contract without depending on downloaded NHS artifacts."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from wardcast.api import create_app


@pytest.fixture
def bundle():
    trust = {
        "code": "R01",
        "name": "Example NHS Trust",
        "region": "North",
        "observations": 2,
        "last_month": "2026-03-01",
        "latest_occupied": 90,
        "latest_available": 100,
        "completeness": 0.5,
    }
    forecast = {
        "code": "R01",
        "cutoff": "2026-03-01",
        "target_month": "2026-04-01",
        "horizon": 1,
        "prediction": 110,
        "lower": 90,
        "upper": 130,
        "actual": None,
        "baseline": 90,
        "model": "persistence",
        "model_version": "test-v1",
        "data_quality_status": "partial_history",
        "explanation": [
            {"feature": "occupied_lag_0", "label": "Latest occupied beds", "value": 90, "contribution": None}
        ],
    }
    previous = {**forecast, "cutoff": "2025-12-01", "target_month": "2026-01-01", "actual": 105}
    return {
        "metadata": {"model_version": "test-v1", "cutoff": "2026-03-01", "nominal_coverage": 0.8},
        "trusts": [trust],
        "history": [
            {
                "code": "R01",
                "name": trust["name"],
                "region": "North",
                "month": "2026-03-01",
                "occupied": 90,
                "available": 100,
                "quality_status": "ok",
                "source_id": "march",
                "occupancy_pct": 90,
            },
            {
                "code": "R01",
                "name": trust["name"],
                "region": "North",
                "month": "2026-02-01",
                "occupied": None,
                "available": None,
                "quality_status": "missing",
                "source_id": "february",
                "occupancy_pct": None,
            },
        ],
        "forecasts": [forecast, previous],
        "evaluation": {
            "primary_metric": "MAE",
            "comparison": [],
            "by_trust": [],
            "by_horizon": [],
            "winter": [],
            "selection": [],
        },
    }


@pytest.fixture
def bundle_path(tmp_path, bundle):
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


@pytest.fixture
def client(bundle_path, tmp_path):
    with TestClient(create_app(bundle_path, static_dir=tmp_path / "absent")) as test_client:
        yield test_client


def test_read_endpoints_keep_missing_values_and_provenance(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/meta").json()["nominal_coverage"] == 0.8
    assert client.get("/api/trusts").json()["trusts"][0]["code"] == "R01"
    history = client.get("/api/history/R01").json()["observations"]
    assert [row["month"] for row in history] == ["2026-02-01", "2026-03-01"]
    assert history[0]["occupied"] is None
    assert history[0]["quality_status"] == "missing"
    assert history[0]["source_id"] == "february"
    assert client.get("/api/evaluation").json()["primary_metric"] == "MAE"


def test_forecasts_default_to_latest_and_allow_replay(client):
    assert client.get("/api/cutoffs/R01").json()["cutoffs"] == ["2026-03-01", "2025-12-01"]
    latest = client.get("/api/forecasts/R01").json()
    assert latest["cutoff"] == "2026-03-01"
    assert latest["model_version"] == "test-v1"
    assert latest["data_quality_status"] == "partial_history"
    assert latest["forecasts"][0]["actual"] is None
    replay = client.get("/api/forecasts/R01", params={"cutoff": "2025-12-01"}).json()
    assert replay["forecasts"][0]["actual"] == 105


def test_scenario_interval_flips_and_demand_stays_fixed(client):
    original = client.get("/api/forecasts/R01").json()
    response = client.post("/api/scenarios", json={"trust_code": "R01", "capacity": 100})
    assert response.status_code == 200
    row = response.json()["forecasts"][0]
    assert row["occupancy_pct"] == pytest.approx(110)
    assert row["margin"] == -10
    assert row["lower_margin"] == -30
    assert row["upper_margin"] == 10
    second = client.post("/api/scenarios", json={"trust_code": "R01", "capacity": 200}).json()["forecasts"][0]
    assert second["occupancy_pct"] == pytest.approx(55)
    assert second["margin"] == 90
    for field in ("prediction", "lower", "upper", "baseline", "model", "explanation"):
        assert row[field] == second[field] == original["forecasts"][0][field]
    assert client.get("/api/forecasts/R01").json() == original


@pytest.mark.parametrize("capacity", [0, -1, "100", "NaN", None, True, 1e-308])
def test_invalid_capacity_is_422(client, capacity):
    result = client.post("/api/scenarios", json={"trust_code": "R01", "capacity": capacity})
    assert result.status_code == 422


@pytest.mark.parametrize("capacity", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_raw_json_rejected_cleanly(client, capacity):
    result = client.post(
        "/api/scenarios",
        content='{"trust_code":"R01","capacity":' + capacity + "}",
        headers={"Content-Type": "application/json"},
    )
    assert result.status_code == 422


@pytest.mark.parametrize("cutoff", ["2026-03-02", "2026-13-01", "2026-3-01", "0000-01-01", "not-a-date"])
def test_invalid_cutoff_is_422(client, cutoff):
    assert client.get("/api/forecasts/R01", params={"cutoff": cutoff}).status_code == 422
    assert (
        client.post(
            "/api/scenarios", json={"trust_code": "R01", "capacity": 100, "cutoff": cutoff}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("endpoint", ["history", "forecasts", "cutoffs"])
def test_unknown_trust_returns_404(client, endpoint):
    assert client.get(f"/api/{endpoint}/UNKNOWN").status_code == 404


def test_unknown_cutoff_and_unexpected_payload_fields(client):
    assert client.get("/api/forecasts/R01?cutoff=2024-01-01").status_code == 404
    assert client.post("/api/scenarios", json={"trust_code": "UNKNOWN", "capacity": 100}).status_code == 404
    assert (
        client.post(
            "/api/scenarios", json={"trust_code": "R01", "capacity": 100, "prediction": 5}
        ).status_code
        == 422
    )


def test_missing_bundle_is_a_useful_503_and_import_does_not_fail(tmp_path):
    test_client = TestClient(create_app(tmp_path / "missing.json"))
    result = test_client.get("/api/health")
    assert result.status_code == 503
    assert "training" in result.json()["detail"]


@pytest.mark.parametrize("corruption", ["nan", "duplicate", "interval", "unknown", "malformed"])
def test_corrupt_bundle_returns_503(tmp_path, bundle, corruption):
    data = copy.deepcopy(bundle)
    if corruption == "nan":
        data["forecasts"][0]["prediction"] = float("nan")
    elif corruption == "duplicate":
        data["history"].append(copy.deepcopy(data["history"][0]))
    elif corruption == "interval":
        data["forecasts"][0]["upper"] = 1
    elif corruption == "unknown":
        data["forecasts"][0]["code"] = "UNKNOWN"
    path = tmp_path / "corrupt.json"
    path.write_text("{" if corruption == "malformed" else json.dumps(data), encoding="utf-8")
    assert TestClient(create_app(path)).get("/api/trusts").status_code == 503


def test_successful_bundle_is_cached_once(client, bundle_path):
    original = client.get("/api/forecasts/R01").json()
    bundle_path.write_text("{}", encoding="utf-8")
    assert client.get("/api/forecasts/R01").json() == original


def test_development_cors_is_limited_to_local_vite(client):
    local = client.get("/api/meta", headers={"Origin": "http://localhost:5173"})
    remote = client.get("/api/meta", headers={"Origin": "https://example.com"})
    assert local.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in remote.headers


def test_frontend_fallback_preserves_api_404_and_blocks_traversal(tmp_path, bundle_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>WardCast</html>", encoding="utf-8")
    (dist / "app.js").write_text("console.log('WardCast')", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")
    web = TestClient(create_app(bundle_path, static_dir=dist))
    assert "WardCast" in web.get("/").text
    assert "WardCast" in web.get("/forecast/R01").text
    assert web.get("/app.js").status_code == 200
    assert web.get("/missing.js").status_code == 404
    assert web.get("/api/missing").status_code == 404
    assert web.get("/%2e%2e/secret.txt").status_code == 404


def test_repository_root_override_applies_to_all_artifacts(tmp_path, bundle, monkeypatch):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/demo.json").write_text(json.dumps(bundle), encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data/source_manifest.json").write_text('{"sources": []}', encoding="utf-8")
    (tmp_path / "frontend/dist").mkdir(parents=True)
    (tmp_path / "frontend/dist/index.html").write_text("<html>Alternate root</html>", encoding="utf-8")
    monkeypatch.setenv("WARDCAST_ROOT", str(tmp_path))
    web = TestClient(create_app())
    assert web.get("/api/health").status_code == 200
    assert web.get("/api/sources").json() == {"sources": []}
    assert "Alternate root" in web.get("/").text
