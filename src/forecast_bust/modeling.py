from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from .constants import ARTIFACTS, REPORTS, TEST_YEAR, TRAIN_YEARS, VALIDATION_YEAR
from .exceptions import ValidationError
from .features import ERROR_COLUMNS, FEATURE_COLUMNS
from .hashing import sha256_file, sha256_json


NUMERIC_FEATURES = sorted(FEATURE_COLUMNS | {"lead_day"})
CATEGORICAL_FEATURES = ["region_id"]
DETERMINISTIC_BASELINE_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
FORBIDDEN_FEATURES = set(ERROR_COLUMNS) | {"severity", "threshold", "bust", "z_precip", "z_mslp", "z_wind", "z_temperature"}
MODEL_VERSION = "xgb-bust-v2-mean-only"


def _year(rows: pl.DataFrame) -> pl.Series:
    return rows["forecast_initialization_time"].str.slice(0, 4).cast(pl.Int32)


def split_rows(rows: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    years = _year(rows)
    train = rows.filter(years.is_in(TRAIN_YEARS))
    validation = rows.filter(years == VALIDATION_YEAR)
    test = rows.filter(years == TEST_YEAR)
    init_sets = [set(frame["forecast_initialization_time"].unique()) for frame in (train, validation, test)]
    if not train.height or not validation.height or not test.height:
        raise ValidationError("Train, validation, and test splits must all be non-empty")
    if init_sets[0] & init_sets[1] or init_sets[0] & init_sets[2] or init_sets[1] & init_sets[2]:
        raise ValidationError("Initialization cycles overlap temporal splits")
    return train, validation, test


def assert_feature_contract(rows: pl.DataFrame) -> None:
    missing = sorted(set(NUMERIC_FEATURES + CATEGORICAL_FEATURES + ["bust"]) - set(rows.columns))
    if missing:
        raise ValidationError(f"Model dataset missing fields: {missing}")
    selected = set(NUMERIC_FEATURES + CATEGORICAL_FEATURES)
    leaked = selected & FORBIDDEN_FEATURES
    if leaked:
        raise ValidationError(f"Verification/target columns selected as features: {sorted(leaked)}")
    if any(name.startswith(("analysis_", "verification_", "e_", "z_")) for name in selected):
        raise ValidationError("Verification-derived field entered the model feature matrix")


def _to_pandas(rows: pl.DataFrame, columns: list[str]):
    return rows.select(columns).to_pandas()


def _climatology(train: pl.DataFrame, target: pl.DataFrame) -> tuple[np.ndarray, dict]:
    mapping = train.group_by(["region_id", "lead_day"]).agg(pl.col("bust").mean().alias("probability"))
    global_probability = float(train["bust"].mean())
    joined = target.select(["region_id", "lead_day"]).join(mapping, on=["region_id", "lead_day"], how="left")
    probability = joined["probability"].fill_null(global_probability).to_numpy()
    return probability.astype(float), {"global_probability": global_probability, "groups": mapping.to_dicts()}


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> tuple[float, list[dict]]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    assignments = np.minimum(np.digitize(p, edges[1:-1], right=False), bins - 1)
    table = []
    total = len(y)
    ece = 0.0
    for index in range(bins):
        mask = assignments == index
        count = int(mask.sum())
        mean_probability = float(p[mask].mean()) if count else None
        observed = float(y[mask].mean()) if count else None
        if count:
            ece += count / total * abs(mean_probability - observed)
        table.append({"bin": index, "lower": float(edges[index]), "upper": float(edges[index + 1]), "count": count, "mean_probability": mean_probability, "observed_frequency": observed})
    return float(ece), table


def evaluate_probabilities(y: np.ndarray, probability: np.ndarray, climatology: np.ndarray) -> tuple[dict, list[dict]]:
    y = np.asarray(y, dtype=int)
    probability = np.clip(np.asarray(probability, dtype=float), 0.0, 1.0)
    climatology = np.clip(np.asarray(climatology, dtype=float), 0.0, 1.0)
    if probability.shape != y.shape or climatology.shape != y.shape:
        raise ValidationError("Probability and label arrays differ in shape")
    brier = float(brier_score_loss(y, probability))
    climatology_brier = float(brier_score_loss(y, climatology))
    threshold = float(np.quantile(probability, 0.8))
    high = probability >= threshold
    positives = int(y.sum())
    recall = float(y[high].sum() / positives) if positives else None
    ece, bins = expected_calibration_error(y, probability)
    metrics = {
        "rows": len(y),
        "prevalence": float(y.mean()),
        "pr_auc": float(average_precision_score(y, probability)) if len(np.unique(y)) > 1 else None,
        "roc_auc": float(roc_auc_score(y, probability)) if len(np.unique(y)) > 1 else None,
        "brier_score": brier,
        "brier_climatology": climatology_brier,
        "brier_skill_score": float(1.0 - brier / climatology_brier) if climatology_brier > 0 else None,
        "expected_calibration_error": ece,
        "top_20_percent_risk_threshold": threshold,
        "top_20_percent_risk_recall": recall,
    }
    return metrics, bins


def _slice_metrics(rows: pl.DataFrame, probability: np.ndarray, climatology: np.ndarray, column: str) -> list[dict]:
    frame = rows.select([column, "bust"]).with_columns(
        pl.Series("probability", probability), pl.Series("climatology", climatology)
    )
    output = []
    for key, group in frame.group_by(column, maintain_order=True):
        metrics, _ = evaluate_probabilities(group["bust"].to_numpy(), group["probability"].to_numpy(), group["climatology"].to_numpy())
        metrics[column] = key[0] if isinstance(key, tuple) else key
        output.append(metrics)
    return sorted(output, key=lambda item: str(item[column]))


def _atomic_joblib(value, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(value, temporary)
    os.replace(temporary, path)


def _atomic_json(value: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def train_and_evaluate(root: Path | None = None, random_state: int = 26079) -> dict:
    data = root / "data" if root else ARTIFACTS.parent
    artifacts = root / "data/artifacts" if root else ARTIFACTS
    reports = root / "data/reports" if root else REPORTS
    labeled_manifest_path = data / "manifests/labeled-dataset-manifest.json"
    if not labeled_manifest_path.exists():
        raise ValidationError("Labeled dataset manifest is missing")
    labeled_manifest = json.loads(labeled_manifest_path.read_text(encoding="utf-8"))
    labeled_paths = sorted((data / "labeled").glob("year=*/month=*/labeled.parquet"))
    if not labeled_paths:
        raise ValidationError("No labeled dataset partitions found")
    if sum(int(item["rows"]) for item in labeled_manifest.get("partitions", [])) != int(labeled_manifest.get("row_count", -1)):
        raise ValidationError("Labeled manifest row count is inconsistent")
    manifest_partitions = {str(Path(item["path"]).resolve()): item for item in labeled_manifest.get("partitions", [])}
    for path in labeled_paths:
        record = manifest_partitions.get(str(path.resolve()))
        if record is None or record.get("sha256") != sha256_file(path):
            raise ValidationError(f"Labeled partition hash is missing or mismatched: {path}")
    rows = pl.read_parquet(labeled_paths)
    assert_feature_contract(rows)
    train, validation, test = split_rows(rows)
    feature_columns = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    preprocessor = ColumnTransformer(
        [("region", OneHotEncoder(handle_unknown="error", sparse_output=True), CATEGORICAL_FEATURES), ("numeric", StandardScaler(), NUMERIC_FEATURES)],
        remainder="drop",
    )
    x_train = preprocessor.fit_transform(_to_pandas(train, feature_columns))
    x_validation = preprocessor.transform(_to_pandas(validation, feature_columns))
    x_test = preprocessor.transform(_to_pandas(test, feature_columns))
    y_train = train["bust"].to_numpy().astype(int)
    y_validation = validation["bust"].to_numpy().astype(int)
    y_test = test["bust"].to_numpy().astype(int)

    candidates = [
        {"max_depth": 3, "learning_rate": 0.05, "n_estimators": 250, "min_child_weight": 5, "subsample": 0.8, "colsample_bytree": 0.8},
        {"max_depth": 5, "learning_rate": 0.05, "n_estimators": 300, "min_child_weight": 5, "subsample": 0.8, "colsample_bytree": 0.8},
        {"max_depth": 4, "learning_rate": 0.08, "n_estimators": 200, "min_child_weight": 10, "subsample": 0.9, "colsample_bytree": 0.9},
        {"max_depth": 6, "learning_rate": 0.04, "n_estimators": 350, "min_child_weight": 10, "subsample": 0.8, "colsample_bytree": 0.8},
    ]
    search = []
    best = None
    for parameters in candidates:
        model = XGBClassifier(
            **parameters,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=random_state,
            n_jobs=-1,
            tree_method="hist",
        )
        model.fit(x_train, y_train)
        raw = model.predict_proba(x_validation)[:, 1]
        score = float(average_precision_score(y_validation, raw))
        search.append({"parameters": parameters, "validation_pr_auc": score})
        if best is None or score > best[0]:
            best = (score, parameters)
    assert best is not None

    classifier = XGBClassifier(
        **best[1], objective="binary:logistic", eval_metric="logloss", random_state=random_state, n_jobs=-1, tree_method="hist"
    )
    classifier.fit(x_train, y_train)
    validation_raw = np.clip(classifier.predict_proba(x_validation)[:, 1], 1e-7, 1 - 1e-7)
    calibrator = LogisticRegression(random_state=random_state, solver="lbfgs")
    calibrator.fit(np.log(validation_raw / (1.0 - validation_raw)).reshape(-1, 1), y_validation)

    linear_baseline = Pipeline([
        ("preprocess", ColumnTransformer([
            ("region", OneHotEncoder(handle_unknown="error"), CATEGORICAL_FEATURES),
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ])),
        ("logistic", LogisticRegression(random_state=random_state, max_iter=1000)),
    ])
    linear_baseline.fit(_to_pandas(train, DETERMINISTIC_BASELINE_FEATURES), y_train)

    evaluations = {}
    prediction_frames = []
    for split_name, frame, matrix, labels in (
        ("validation_2021", validation, x_validation, y_validation),
        ("test_2022", test, x_test, y_test),
    ):
        raw = np.clip(classifier.predict_proba(matrix)[:, 1], 1e-7, 1 - 1e-7)
        calibrated = calibrator.predict_proba(np.log(raw / (1.0 - raw)).reshape(-1, 1))[:, 1]
        climatology, climatology_artifact = _climatology(train, frame)
        linear = linear_baseline.predict_proba(_to_pandas(frame, DETERMINISTIC_BASELINE_FEATURES))[:, 1]
        metrics, calibration_bins = evaluate_probabilities(labels, calibrated, climatology)
        linear_metrics, _ = evaluate_probabilities(labels, linear, climatology)
        climatology_metrics, _ = evaluate_probabilities(labels, climatology, climatology)
        evaluations[split_name] = {
            "model": metrics,
            "climatology_baseline": climatology_metrics,
            "logistic_regression_baseline": linear_metrics,
            "calibration_bins": calibration_bins,
            "by_lead_day": _slice_metrics(frame, calibrated, climatology, "lead_day"),
            "by_region": _slice_metrics(frame, calibrated, climatology, "region_id"),
        }
        prediction_frames.append(
            frame.select(["region_id", "lead_day", "forecast_initialization_time", "valid_time", "bust"]).with_columns(
                pl.lit(split_name).alias("split"),
                pl.Series("raw_probability", raw),
                pl.Series("bust_probability", calibrated),
                pl.Series("climatology_probability", climatology),
                pl.Series("logistic_baseline_probability", linear),
            )
        )

    artifacts.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    paths = {
        "preprocessor": artifacts / "preprocessor.joblib",
        "classifier": artifacts / "xgboost-classifier.joblib",
        "calibrator": artifacts / "sigmoid-calibrator.joblib",
        "logistic_baseline": artifacts / "logistic-baseline.joblib",
        "climatology": artifacts / "climatology.json",
    }
    _atomic_joblib(preprocessor, paths["preprocessor"])
    _atomic_joblib(classifier, paths["classifier"])
    _atomic_joblib(calibrator, paths["calibrator"])
    _atomic_joblib(linear_baseline, paths["logistic_baseline"])
    _, climatology_artifact = _climatology(train, validation)
    _atomic_json(climatology_artifact, paths["climatology"])
    predictions_path = reports / "held-out-predictions.parquet"
    temporary_predictions = predictions_path.with_suffix(".parquet.tmp")
    pl.concat(prediction_frames).write_parquet(temporary_predictions)
    os.replace(temporary_predictions, predictions_path)

    metadata = {
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "random_state": random_state,
        "fit_years": list(TRAIN_YEARS),
        "validation_year": VALIDATION_YEAR,
        "calibration_fit_year": VALIDATION_YEAR,
        "test_year": TEST_YEAR,
        "classifier_training_rows": train.height,
        "calibrator_training_rows": validation.height,
        "feature_columns": feature_columns,
        "categorical_features": CATEGORICAL_FEATURES,
        "forbidden_features": sorted(FORBIDDEN_FEATURES),
        "selected_parameters": best[1],
        "hyperparameter_search": search,
        "evaluations": evaluations,
        "artifacts": {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in paths.items()},
        "predictions": {"path": str(predictions_path), "sha256": sha256_file(predictions_path)},
    }
    metadata["content_sha256"] = sha256_json(metadata)
    report_path = reports / "model-evaluation.json"
    _atomic_json(metadata, report_path)
    return {
        "report": str(report_path),
        "model_version": MODEL_VERSION,
        "selected_parameters": best[1],
        "validation": evaluations["validation_2021"]["model"],
        "test": evaluations["test_2022"]["model"],
        "artifacts": {name: str(path) for name, path in paths.items()},
    }
