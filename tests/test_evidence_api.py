import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from forecast_bust.api import app
from forecast_bust.evidence import EXCLUDED_FIELDS, EvidenceEngine
from forecast_bust.identity import prediction_id
from forecast_bust.modeling import NUMERIC_FEATURES


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def snapshot():
    return json.loads((Path(__file__).parent / "fixtures/api-contract-snapshot.json").read_text())


def test_health_model_runs_and_canonical_regions(client, snapshot):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok", "model_loaded": True,
        "model_version": snapshot["model_version"], "dataset_version": snapshot["dataset_version"],
    }
    model = client.get("/v1/model").json()
    assert model["feature_contract"] == snapshot["feature_contract"]
    assert model["training_years"] == [2018, 2019, 2020]
    assert model["validation_year"] == 2021 and model["test_year"] == 2022
    assert model["held_out_metrics"]["model"]["pr_auc"] == pytest.approx(0.7540872881483971)
    runs = client.get("/v1/runs").json()
    assert runs[0]["run_id"] == snapshot["example_run_id"]
    assert runs == sorted(runs, key=lambda item: item["source_forecast_time"], reverse=True)
    regions = client.get("/v1/regions").json()
    assert len(regions) == 36
    assert [item["region_id"] for item in regions] == [f"imd-{value:02d}" for value in range(1, 37)]
    assert all(item["geometry_reference"].startswith("/v1/regions/geojson#imd-") for item in regions)


def test_local_frontend_cors_is_read_only(client):
    response = client.options(
        "/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_risk_map_contract_probability_identity_and_errors(client, snapshot):
    response = client.get("/v1/risk-map", params={"run_id": snapshot["example_run_id"], "lead_day": 1})
    assert response.status_code == 200
    risks = response.json()["risks"]
    assert len(risks) == snapshot["risk_map_count"]
    assert [item["region_id"] for item in risks] == sorted(item["region_id"] for item in risks)
    first = risks[0]
    assert first["prediction_id"] == snapshot["example_prediction_id"]
    assert first["bust_probability"] == pytest.approx(snapshot["example_bust_probability"])
    assert first["forecast_reliability"] == 1.0 - first["bust_probability"]
    assert first["forecast_confidence"] == first["forecast_reliability"]
    assert first["provenance"]["raw_ensemble_member_access"] is False
    assert client.get("/v1/risk-map", params={"run_id": snapshot["example_run_id"], "lead_day": 11}).status_code == 422
    assert client.get("/v1/risk-map", params={"run_id": "run-20000101T000000Z", "lead_day": 1}).status_code == 404


def test_lead_curve_is_ordered_and_prediction_id_is_stable(client, snapshot):
    response = client.get(f"/v1/regions/{snapshot['example_region_id']}/lead-curve", params={"run_id": snapshot["example_run_id"]})
    assert response.status_code == 200
    points = response.json()["points"]
    assert len(points) == snapshot["lead_curve_count"]
    assert [item["lead_day"] for item in points] == list(range(1, 11))
    expected = prediction_id(snapshot["model_version"], "2022-09-30T12:00:00.000000000", "imd-01", 1)
    assert points[0]["prediction_id"] == expected == snapshot["example_prediction_id"]
    assert client.get("/v1/regions/imd-99/lead-curve", params={"run_id": snapshot["example_run_id"]}).status_code == 404


def test_explanation_is_deterministic_grounded_and_uses_training_only_analogs(client, snapshot):
    url = f"/v1/predictions/{snapshot['example_prediction_id']}/explanation"
    first = client.get(url)
    second = client.get(url)
    assert first.status_code == 200 and first.json() == second.json()
    value = first.json()
    assert value["bust_probability"] == pytest.approx(snapshot["example_bust_probability"])
    assert value["forecast_reliability"] == 1.0 - value["bust_probability"]
    names = [item["feature_name"] for item in value["feature_values"]]
    assert names == ["region_id", "lead_day", "mslp_gradient_pa_per_km", "mslp_mean_pa", "precip24_mean_mm", "run_to_run_mslp_drift_pa", "season_cos", "season_sin", "temperature2m_mean_k", "thickness500_850_m", "u10_mean_mps", "v10_mean_mps", "vorticity850_s1", "wind10_mean_mps", "wind850_mean_mps"]
    assert not set(names) & EXCLUDED_FIELDS
    drivers = value["top_positive_drivers"] + value["top_negative_drivers"]
    assert all(item["unit"] is not None for item in drivers if item["feature_name"] not in {"region_id", "season_sin", "season_cos"})
    assert all("caused" not in item["interpretation"] for item in drivers)
    assert [item["shap_value"] for item in value["top_positive_drivers"]] == sorted([item["shap_value"] for item in value["top_positive_drivers"]], reverse=True)
    analogs = value["historical_analogs"]
    assert len(analogs) == snapshot["analog_count"]
    assert all(item["initialization_time"][:4] in {"2018", "2019", "2020"} for item in analogs)
    assert all(item["region_id"] == snapshot["example_region_id"] and item["lead_day"] == 1 for item in analogs)
    assert all(item["initialization_time"] != value["source_forecast_time"] for item in analogs)
    assert [(item["distance"], item["initialization_time"], item["lead_day"]) for item in analogs] == sorted((item["distance"], item["initialization_time"], item["lead_day"]) for item in analogs)
    assert value["provenance"]["prediction_artifact_sha256"]
    assert client.get("/v1/predictions/not-a-prediction/explanation").status_code == 404


def test_explanation_replays_the_original_float32_calibration_path(client, snapshot):
    day_two_id = prediction_id(
        snapshot["model_version"], "2022-09-30T12:00:00.000000000", "imd-01", 2,
    )
    response = client.get(f"/v1/predictions/{day_two_id}/explanation")
    assert response.status_code == 200
    assert response.json()["prediction_id"] == day_two_id


def test_analog_scaler_manifest_is_training_only_and_hashed():
    manifest_path = Path("data/artifacts/analog-scaler-manifest.json")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["fit_years"] == [2018, 2019, 2020]
    assert manifest["fit_rows"] == 263520
    assert manifest["sha256"]


def test_analog_fallback_preserves_same_lead_priority_and_tie_order():
    def candidate(initialization, lead_day, value):
        row = {name: value for name in NUMERIC_FEATURES}
        row.update({
            "forecast_initialization_time": initialization,
            "valid_time": "2020-06-10T00:00:00.000000000",
            "region_id": "imd-01", "region_name": "Lakshadweep", "lead_day": lead_day,
            "bust": 0, "severity": 0.0, "dataset_version": "wb2-ifs-mean-india-v2",
            "e_precip_mm": 0.0, "e_wind_mps": 0.0, "e_temperature_k": 0.0, "e_mslp_pa": 0.0,
        })
        return row

    same_lead = [
        candidate("2020-06-02T00:00:00.000000000", 5, 1.0),
        candidate("2020-06-01T00:00:00.000000000", 5, -1.0),
        candidate("2022-06-01T00:00:00.000000000", 5, 0.0),
    ]
    fallback = same_lead + [candidate("2019-06-01T00:00:00.000000000", 4, 0.01)]
    store = SimpleNamespace(analog_candidates=lambda _region, lead: same_lead if lead == 5 else fallback)
    engine = EvidenceEngine.__new__(EvidenceEngine)
    engine.store = store
    engine.analog_scaler = SimpleNamespace(transform=lambda frame: np.asarray(frame, dtype=float))
    query = candidate("2022-06-01T00:00:00.000000000", 5, 0.0)

    analogs = engine.analogs(query)

    assert [(item.initialization_time, item.lead_day) for item in analogs] == [
        ("2020-06-01T00:00:00.000000000", 5),
        ("2020-06-02T00:00:00.000000000", 5),
        ("2019-06-01T00:00:00.000000000", 4),
    ]
