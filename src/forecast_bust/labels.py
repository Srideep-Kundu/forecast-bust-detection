from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from .constants import (
    ARTIFACTS,
    MANIFESTS,
    MIN_GROUP_SAMPLES,
    PROCESSED,
    ROBUST_CLIP,
    ROBUST_EPSILON,
    TRAIN_YEARS,
)
from .exceptions import ValidationError
from .hashing import sha256_file, sha256_json


COMPONENTS = {
    "precip": "e_precip_mm",
    "mslp": "e_mslp_pa",
    "wind": "e_wind_mps",
    "temperature": "e_temperature_k",
}
SEVERITY_WEIGHTS = {"precip": 0.40, "mslp": 0.20, "wind": 0.20, "temperature": 0.20}


def _year_expression() -> pl.Expr:
    return pl.col("forecast_initialization_time").str.slice(0, 4).cast(pl.Int32)


def _median_mad(values: np.ndarray) -> tuple[float, float, int]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValidationError("Cannot fit robust statistics on an empty sample")
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return median, mad, int(values.size)


def _fit_component(train: pl.DataFrame, column: str, groups: list[dict]) -> list[dict]:
    global_stats = _median_mad(train[column].to_numpy())
    lead_values = {
        int(key[0] if isinstance(key, tuple) else key): _median_mad(group[column].to_numpy())
        for key, group in train.group_by("lead_day")
    }
    group_values = {
        (str(key[0]), int(key[1])): _median_mad(group[column].to_numpy())
        for key, group in train.group_by(["region_id", "lead_day"])
    }
    output = []
    for group in groups:
        key = (str(group["region_id"]), int(group["lead_day"]))
        direct = group_values.get(key)
        lead = lead_values.get(key[1])
        if direct and direct[2] >= MIN_GROUP_SAMPLES:
            selected, level = direct, "region_lead"
        elif lead and lead[2] >= MIN_GROUP_SAMPLES:
            selected, level = lead, "lead"
        else:
            selected, level = global_stats, "global"
        output.append(
            {
                "region_id": key[0],
                "lead_day": key[1],
                "median": selected[0],
                "mad": selected[1],
                "sample_count": selected[2],
                "fallback_level": level,
            }
        )
    return output


def _apply_standardization(rows: pl.DataFrame, statistics: dict[str, list[dict]]) -> pl.DataFrame:
    result = rows
    for component, error_column in COMPONENTS.items():
        stat = pl.DataFrame(statistics[component]).select(
            "region_id",
            "lead_day",
            pl.col("median").alias(f"_{component}_median"),
            pl.col("mad").alias(f"_{component}_mad"),
        )
        result = result.join(stat, on=["region_id", "lead_day"], how="left")
        if result[f"_{component}_median"].null_count():
            raise ValidationError(f"Missing fitted statistics for {component}")
        denominator = 1.4826 * pl.col(f"_{component}_mad") + ROBUST_EPSILON
        result = result.with_columns(
            ((pl.col(error_column) - pl.col(f"_{component}_median")) / denominator)
            .clip(ROBUST_CLIP[0], ROBUST_CLIP[1])
            .alias(f"z_{component}")
        ).drop([f"_{component}_median", f"_{component}_mad"])
    return result.with_columns(
        sum(pl.col(f"z_{name}") * weight for name, weight in SEVERITY_WEIGHTS.items()).alias("severity")
    )


def fit_label_artifacts(rows: pl.DataFrame) -> tuple[dict, pl.DataFrame]:
    train = rows.with_columns(_year_expression().alias("_year")).filter(pl.col("_year").is_in(TRAIN_YEARS)).drop("_year")
    if train.is_empty():
        raise ValidationError("No 2018-2020 rows available for label fitting")
    groups = rows.select(["region_id", "lead_day"]).unique().sort(["region_id", "lead_day"]).to_dicts()
    statistics = {name: _fit_component(train, column, groups) for name, column in COMPONENTS.items()}
    standardized_train = _apply_standardization(train, statistics)
    thresholds = (
        standardized_train.group_by(["region_id", "lead_day"])
        .agg(pl.col("severity").quantile(0.85, interpolation="linear").alias("threshold"), pl.len().alias("sample_count"))
        .sort(["region_id", "lead_day"])
    )
    if thresholds.height != len(groups):
        raise ValidationError(f"Threshold groups={thresholds.height}; expected={len(groups)}")
    artifact = {
        "artifact_type": "forecast_bust_label_transform",
        "fit_years": list(TRAIN_YEARS),
        "minimum_group_samples": MIN_GROUP_SAMPLES,
        "epsilon": ROBUST_EPSILON,
        "clip": list(ROBUST_CLIP),
        "components": COMPONENTS,
        "severity_weights": SEVERITY_WEIGHTS,
        "statistics": statistics,
        "threshold_quantile": 0.85,
        "thresholds": thresholds.to_dicts(),
    }
    artifact["content_sha256"] = sha256_json(artifact)
    return artifact, standardized_train


def apply_label_artifacts(rows: pl.DataFrame, artifact: dict) -> pl.DataFrame:
    standardized = _apply_standardization(rows, artifact["statistics"])
    thresholds = pl.DataFrame(artifact["thresholds"]).select("region_id", "lead_day", "threshold")
    result = standardized.join(thresholds, on=["region_id", "lead_day"], how="left")
    if result["threshold"].null_count():
        raise ValidationError("Missing training-only bust threshold")
    return result.with_columns((pl.col("severity") > pl.col("threshold")).cast(pl.Int8).alias("bust"))


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def label_full_corpus(root: Path | None = None) -> dict:
    processed = root / "data/processed" if root else PROCESSED
    artifacts = root / "data/artifacts" if root else ARTIFACTS
    manifests = root / "data/manifests" if root else MANIFESTS
    corpus_manifest_path = manifests / "full-dataset-manifest.json"
    if not corpus_manifest_path.exists():
        raise ValidationError("Full dataset manifest is missing")
    corpus_manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    if corpus_manifest.get("status") != "complete" or corpus_manifest.get("missing_initializations"):
        raise ValidationError("Full dataset manifest is incomplete; resume build-full before labeling")
    paths = sorted(processed.glob("year=*/month=*/init=*.parquet"))
    if not paths:
        raise ValidationError("No full-corpus partitions found")
    rows = pl.read_parquet(paths)
    artifact, _ = fit_label_artifacts(rows)
    artifacts.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts / "label-transform.json"
    _atomic_json(artifact_path, artifact)
    labeled = apply_label_artifacts(rows, artifact).with_columns(_year_expression().alias("_year"))
    output_root = (root / "data/labeled" if root else processed.parent / "labeled")
    partition_records = []
    for keys, frame in labeled.with_columns(
        pl.col("forecast_initialization_time").str.slice(5, 2).cast(pl.Int8).alias("_month")
    ).group_by(["_year", "_month"], maintain_order=True):
        year, month = int(keys[0]), int(keys[1])
        path = output_root / f"year={year}" / f"month={month:02d}" / "labeled.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".parquet.tmp")
        frame.drop(["_year", "_month"]).sort(["forecast_initialization_time", "lead_day", "region_id"]).write_parquet(temporary)
        os.replace(temporary, path)
        partition_records.append({"path": str(path), "rows": frame.height, "sha256": sha256_file(path)})
    prevalence = (
        labeled.group_by("_year").agg(pl.len().alias("rows"), pl.col("bust").mean().alias("bust_prevalence")).sort("_year")
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "label_artifact": str(artifact_path),
        "label_artifact_sha256": sha256_file(artifact_path),
        "row_count": labeled.height,
        "partitions": partition_records,
        "prevalence_by_year": prevalence.to_dicts(),
    }
    manifest_path = manifests / "labeled-dataset-manifest.json"
    _atomic_json(manifest_path, manifest)
    return {"manifest": str(manifest_path), "label_artifact": str(artifact_path), "rows": labeled.height, "prevalence": prevalence.to_dicts()}
