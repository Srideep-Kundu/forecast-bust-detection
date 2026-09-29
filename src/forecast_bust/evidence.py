from __future__ import annotations

import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from xgboost import DMatrix

from .constants import ARTIFACTS, DATA, DATASET_VERSION, FEATURE_CONTRACT_VERSION, REPORTS, TRAIN_YEARS
from .contracts import AnalogEvent, FeatureValue, PredictionExplanation, ShapDriver
from .data_store import ArtifactStore
from .exceptions import ValidationError
from .hashing import sha256_file, sha256_json
from .identity import prediction_id, run_id
from .modeling import MODEL_VERSION, NUMERIC_FEATURES


FEATURE_METADATA = {
    "region_id": ("Region", None),
    "lead_day": ("Forecast Lead", "day"),
    "mslp_gradient_pa_per_km": ("MSLP Gradient", "Pa/km"),
    "mslp_mean_pa": ("Mean Sea-Level Pressure", "Pa"),
    "precip24_mean_mm": ("24-hour Precipitation", "mm"),
    "run_to_run_mslp_drift_pa": ("Run-to-run MSLP Drift", "Pa"),
    "season_cos": ("Season Cosine", None),
    "season_sin": ("Season Sine", None),
    "temperature2m_mean_k": ("2 m Temperature", "K"),
    "thickness500_850_m": ("500–850 hPa Thickness", "m"),
    "u10_mean_mps": ("10 m Zonal Wind", "m/s"),
    "v10_mean_mps": ("10 m Meridional Wind", "m/s"),
    "vorticity850_s1": ("850 hPa Relative Vorticity", "s^-1"),
    "wind10_mean_mps": ("10 m Wind Speed", "m/s"),
    "wind850_mean_mps": ("850 hPa Wind Speed", "m/s"),
}
EXCLUDED_FIELDS = {"e_precip_mm", "e_wind_mps", "e_temperature_k", "e_mslp_pa", "severity", "threshold", "bust", "z_precip", "z_mslp", "z_wind", "z_temperature"}


def build_analog_artifacts(data_root: Path = DATA) -> dict:
    store = ArtifactStore(data_root)
    columns = list(NUMERIC_FEATURES)
    rows = store.query(
        f"SELECT {','.join(columns)} FROM labeled WHERE CAST(substr(forecast_initialization_time,1,4) AS INTEGER) BETWEEN 2018 AND 2020"
    )
    if not rows:
        raise ValidationError("Training-only analog pool is empty")
    matrix = pd.DataFrame(rows, columns=columns)
    scaler = StandardScaler().fit(matrix)
    artifacts = data_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    scaler_path = artifacts / "analog-scaler.joblib"
    temporary = scaler_path.with_suffix(".joblib.tmp")
    joblib.dump(scaler, temporary)
    os.replace(temporary, scaler_path)
    manifest = {
        "artifact": str(scaler_path),
        "sha256": sha256_file(scaler_path),
        "dataset_version": DATASET_VERSION,
        "feature_contract": FEATURE_CONTRACT_VERSION,
        "fit_years": list(TRAIN_YEARS),
        "fit_rows": len(rows),
        "feature_columns": columns,
        "source_label_manifest_sha256": sha256_file(data_root / "manifests/labeled-dataset-manifest.json"),
    }
    manifest["content_sha256"] = sha256_json(manifest)
    manifest_path = artifacts / "analog-scaler-manifest.json"
    temp_manifest = manifest_path.with_suffix(".json.tmp")
    temp_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp_manifest, manifest_path)
    return {"manifest": str(manifest_path), **manifest}


class EvidenceEngine:
    def __init__(self, store: ArtifactStore):
        self.store = store
        report = store.report
        self.model_version = report["model_version"]
        self.feature_columns = report["feature_columns"]
        if set(self.feature_columns) & EXCLUDED_FIELDS:
            raise ValidationError("Excluded target/verification fields appear in the saved model contract")
        self.preprocessor = joblib.load(report["artifacts"]["preprocessor"]["path"])
        self.classifier = joblib.load(report["artifacts"]["classifier"]["path"])
        self.calibrator = joblib.load(report["artifacts"]["calibrator"]["path"])
        manifest_path = store.data_root / "artifacts/analog-scaler-manifest.json"
        if not manifest_path.exists():
            raise ValidationError("Analog scaler manifest is missing; run forecast-bust build-evidence")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scaler_path = store.resolve_recorded_path(manifest["artifact"])
        if sha256_file(scaler_path) != manifest["sha256"] or manifest["fit_years"] != list(TRAIN_YEARS):
            raise ValidationError("Analog scaler artifact is invalid or not training-only")
        if manifest["feature_columns"] != list(NUMERIC_FEATURES):
            raise ValidationError("Analog scaler feature contract mismatch")
        if manifest.get("source_label_manifest_sha256") != sha256_file(store.label_manifest_path):
            raise ValidationError("Analog scaler source manifest no longer matches the labeled dataset")
        self.analog_manifest = manifest
        self.analog_scaler = joblib.load(scaler_path)
        self.transformed_names = self.preprocessor.get_feature_names_out().tolist()

    def _feature_frame(self, row: dict) -> pd.DataFrame:
        return pd.DataFrame([{name: row[name] for name in self.feature_columns}], columns=self.feature_columns)

    def shap_values(self, row: dict) -> tuple[float, list[FeatureValue], list[ShapDriver], list[ShapDriver]]:
        transformed = self.preprocessor.transform(self._feature_frame(row))
        contributions = self.classifier.get_booster().predict(DMatrix(transformed), pred_contribs=True)[0]
        base_value = float(contributions[-1])
        shap_by_feature = {name: 0.0 for name in self.feature_columns}
        for name, value in zip(self.transformed_names, contributions[:-1], strict=True):
            original = "region_id" if name.startswith("region__region_id_") else name.removeprefix("numeric__")
            if original not in shap_by_feature:
                raise ValidationError(f"Unexpected transformed SHAP feature: {name}")
            shap_by_feature[original] += float(value)
        raw_margin = float(self.classifier.get_booster().predict(DMatrix(transformed), output_margin=True)[0])
        if not np.isclose(base_value + sum(shap_by_feature.values()), raw_margin, atol=1e-5):
            raise ValidationError("TreeSHAP contributions do not reconstruct the raw model margin")
        values = []
        drivers = []
        for feature in self.feature_columns:
            display, unit = FEATURE_METADATA[feature]
            value = row[feature]
            values.append(FeatureValue(feature_name=feature, display_name=display, value=value, unit=unit))
            contribution = shap_by_feature[feature]
            direction = "increased" if contribution >= 0 else "decreased"
            drivers.append(ShapDriver(
                feature_name=feature, display_name=display, value=value, unit=unit,
                shap_value=contribution, direction=direction,
                interpretation=f"This feature {direction} the model's predicted bust risk.",
            ))
        positive = sorted((item for item in drivers if item.shap_value > 0), key=lambda item: (-item.shap_value, item.feature_name))[:5]
        negative = sorted((item for item in drivers if item.shap_value < 0), key=lambda item: (item.shap_value, item.feature_name))[:5]
        return base_value, values, positive, negative

    def analogs(self, row: dict) -> list[AnalogEvent]:
        def eligible(items: list[dict]) -> list[dict]:
            return [item for item in items if item["forecast_initialization_time"] != row["forecast_initialization_time"]]

        query = pd.DataFrame([{name: row[name] for name in NUMERIC_FEATURES}], columns=NUMERIC_FEATURES)
        query_z = self.analog_scaler.transform(query)[0]

        def ranked(items: list[dict]) -> list[tuple[dict, float]]:
            if not items:
                return []
            frame = pd.DataFrame([{name: item[name] for name in NUMERIC_FEATURES} for item in items], columns=NUMERIC_FEATURES)
            distances = np.linalg.norm(self.analog_scaler.transform(frame) - query_z, axis=1)
            return sorted(
                zip(items, distances, strict=True),
                key=lambda pair: (float(pair[1]), pair[0]["forecast_initialization_time"], int(pair[0]["lead_day"])),
            )

        same_lead = eligible(self.store.analog_candidates(row["region_id"], int(row["lead_day"])))
        selected = ranked(same_lead)[:3]
        if len(selected) < 3:
            selected_keys = {(item["forecast_initialization_time"], int(item["lead_day"])) for item, _ in selected}
            fallback = [
                item for item in eligible(self.store.analog_candidates(row["region_id"], None))
                if (item["forecast_initialization_time"], int(item["lead_day"])) not in selected_keys
                and int(item["lead_day"]) != int(row["lead_day"])
            ]
            selected.extend(ranked(fallback)[:3-len(selected)])
        return [AnalogEvent(
            initialization_time=item["forecast_initialization_time"], valid_time=item["valid_time"],
            region_id=item["region_id"], region_name=item["region_name"], lead_day=int(item["lead_day"]),
            distance=float(distance), bust=int(item["bust"]), severity=float(item["severity"]),
            forecast_feature_summary={name: float(item[name]) for name in ("mslp_mean_pa", "precip24_mean_mm", "run_to_run_mslp_drift_pa", "wind10_mean_mps")},
            retrospective_error_summary={name: float(item[name]) for name in ("e_precip_mm", "e_wind_mps", "e_temperature_k", "e_mslp_pa")},
            dataset_version=item["dataset_version"],
        ) for item, distance in selected]

    def _validate_authoritative_probability(self, row: dict) -> None:
        transformed = self.preprocessor.transform(self._feature_frame(row))
        # Training calibrated XGBoost's native float32 score array. Preserve that
        # exact numerical path here; promoting the scalar before the logit changes
        # valid probabilities by up to a few e-8 and creates a false artifact error.
        raw_array = np.asarray(self.classifier.predict_proba(transformed)[:, 1], dtype=np.float32)
        raw_array = np.clip(raw_array, np.float32(1e-7), np.float32(1.0 - 1e-7))
        raw = float(raw_array[0])
        logits = np.log(raw_array / (np.float32(1.0) - raw_array)).reshape(-1, 1)
        calibrated = float(self.calibrator.predict_proba(logits)[0, 1])
        if not np.isclose(raw, float(row["raw_probability"]), rtol=0.0, atol=1e-7):
            raise ValidationError("Stored raw model output does not match the frozen classifier")
        if not np.isclose(calibrated, float(row["bust_probability"]), rtol=0.0, atol=1e-10):
            raise ValidationError("Stored calibrated probability does not match the frozen calibrator")

    def explain(self, row: dict, provenance: dict) -> PredictionExplanation:
        self._validate_authoritative_probability(row)
        base, values, positive, negative = self.shap_values(row)
        probability = float(row["bust_probability"])
        return PredictionExplanation(
            prediction_id=prediction_id(self.model_version, row["forecast_initialization_time"], row["region_id"], int(row["lead_day"])),
            run_id=run_id(row["forecast_initialization_time"]), region_id=row["region_id"], region_name=row["region_name"],
            lead_day=int(row["lead_day"]), source_forecast_time=row["forecast_initialization_time"], valid_time=row["valid_time"],
            raw_model_output=float(row["raw_probability"]), bust_probability=probability, forecast_reliability=1.0-probability,
            model_version=self.model_version, dataset_version=row["dataset_version"], base_value=base,
            top_positive_drivers=positive, top_negative_drivers=negative, feature_values=values,
            historical_analogs=self.analogs(row), provenance=provenance,
        )
