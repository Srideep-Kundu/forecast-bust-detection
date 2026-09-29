import numpy as np
import polars as pl
import pytest
import json

from forecast_bust.exceptions import ValidationError
from forecast_bust.features import FEATURE_COLUMNS
from forecast_bust.hashing import sha256_file
from forecast_bust.modeling import DETERMINISTIC_BASELINE_FEATURES, NUMERIC_FEATURES, assert_feature_contract, evaluate_probabilities, split_rows, train_and_evaluate


def _model_rows() -> pl.DataFrame:
    records = []
    for year in range(2018, 2023):
        for index in range(20):
            row = {name: float(index + 1) for name in FEATURE_COLUMNS}
            row.update(
                {
                    "region_id": f"imd-{index % 2 + 1:02d}",
                    "lead_day": index % 10 + 1,
                    "forecast_initialization_time": f"{year}-06-{index % 20 + 1:02d}T00:00:00.000000000",
                    "bust": index % 3 == 0,
                }
            )
            records.append(row)
    return pl.DataFrame(records)


def test_feature_contract_and_temporal_splits():
    rows = _model_rows()
    assert_feature_contract(rows)
    train, validation, test = split_rows(rows)
    assert train.height == 60
    assert validation.height == 20
    assert test.height == 20
    assert not any("spread" in name for name in FEATURE_COLUMNS)
    assert not any("spread" in name for name in NUMERIC_FEATURES)
    assert set(DETERMINISTIC_BASELINE_FEATURES) == {"region_id", *NUMERIC_FEATURES}


def test_feature_contract_rejects_missing_model_field():
    with pytest.raises(ValidationError, match="missing fields"):
        assert_feature_contract(_model_rows().drop("precip24_mean_mm"))


def test_metrics_probability_range_bss_and_bins():
    y = np.array([0, 0, 1, 1])
    probability = np.array([0.1, 0.2, 0.8, 0.9])
    climatology = np.full(4, 0.5)
    metrics, bins = evaluate_probabilities(y, probability, climatology)
    assert metrics["brier_skill_score"] == pytest.approx(1 - metrics["brier_score"] / 0.25)
    assert metrics["pr_auc"] == pytest.approx(1.0)
    assert len(bins) == 10
    assert all(0 <= value <= 1 for value in probability)


def test_training_writes_separate_hashed_classifier_and_calibrator(tmp_path):
    rng = np.random.default_rng(26079)
    records = []
    for year in range(2018, 2023):
        for index in range(160):
            signal = rng.normal()
            row = {name: float(rng.normal()) for name in FEATURE_COLUMNS}
            row.update(
                {
                    "region_id": f"imd-{index % 4 + 1:02d}",
                    "lead_day": index % 10 + 1,
                    "forecast_initialization_time": f"{year}-06-{index % 28 + 1:02d}T{(index // 28) % 2 * 12:02d}:00:00.000000000",
                    "valid_time": f"{year}-06-{index % 28 + 1:02d}T00:00:00.000000000",
                    "bust": int(signal + 0.7 * row["precip24_mean_mm"] > 0.5),
                }
            )
            records.append(row)
    path = tmp_path / "data/labeled/year=2018/month=06/labeled.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame(records).write_parquet(path)
    manifest_path = tmp_path / "data/manifests/labeled-dataset-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps({"row_count": len(records), "partitions": [{"path": str(path), "rows": len(records), "sha256": sha256_file(path)}]}), encoding="utf-8")
    result = train_and_evaluate(root=tmp_path)
    classifier = tmp_path / "data/artifacts/xgboost-classifier.joblib"
    calibrator = tmp_path / "data/artifacts/sigmoid-calibrator.joblib"
    assert classifier.exists() and calibrator.exists()
    assert classifier != calibrator
    assert sha256_file(classifier) != sha256_file(calibrator)
    assert 0 <= result["test"]["brier_score"] <= 1
    assert len(result["test"]) >= 10
