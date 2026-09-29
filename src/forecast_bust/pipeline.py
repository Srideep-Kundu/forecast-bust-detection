from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from .constants import CACHE, DATASET_VERSION, GEOMETRY, LEAD_HOURS, MANIFESTS, PROCESSED, WEIGHTS
from .exceptions import ValidationError
from .features import assert_feature_timestamp_isolation, build_forecast_feature_rows, build_verification_error_rows, precipitation_to_mm
from .geometry import acquire_geometry, compute_region_weights, load_expected_manifest, validate_and_canonicalize_geometry
from .hashing import sha256_file
from .manifest import build_manifest, write_manifest
from .regrid import align_to_target
from .weatherbench import lead_hours_values, lead_selector, open_mean_sources_and_validate, select_india


FORECAST_VARIABLES = [
    "mean_sea_level_pressure",
    "2m_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "u_component_of_wind",
    "v_component_of_wind",
    "geopotential",
    "total_precipitation_24hr",
]
ANALYSIS_STATE_VARIABLES = ["mean_sea_level_pressure", "2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind"]


def _validate_request(initialization: np.datetime64, lead_hours: int) -> None:
    if lead_hours not in LEAD_HOURS:
        raise ValidationError(f"lead_hours={lead_hours}; require one of {LEAD_HOURS}")
    text = str(np.datetime64(initialization, "h"))
    year, month = int(text[:4]), int(text[5:7])
    if not 2018 <= year <= 2022 or month not in (6, 7, 8, 9):
        raise ValidationError("Smoke initialization must be within June-September 2018-2022")


def compose_derived_rows(features: pl.DataFrame, errors: pl.DataFrame) -> pl.DataFrame:
    assert_feature_timestamp_isolation(features)
    rows = features.join(errors, on=["region_id", "region_name"], how="inner")
    rows = rows.with_columns(
        pl.col("region_id").map_elements(lambda value: f"imd-{value:02d}", return_dtype=pl.String),
        pl.lit(DATASET_VERSION).alias("dataset_version"),
        pl.lit("categorical").alias("region_id_semantics"),
    ).sort("region_id")
    assert_feature_timestamp_isolation(rows)
    nonfinite = [name for name in rows.columns if rows[name].dtype.is_numeric() and not rows[name].is_finite().all()]
    if nonfinite:
        raise ValidationError(f"Derived rows contain non-finite numeric columns: {nonfinite}")
    return rows


def run_smoke(initialization: str = "2020-06-01T00:00:00", lead_hours: int = 24, root: Path | None = None) -> dict:
    init = np.datetime64(initialization, "ns")
    _validate_request(init, lead_hours)
    cache = (root / "data/cache") if root else CACHE
    geometry_dir = (root / "data/geometry") if root else GEOMETRY
    weights_dir = (root / "data/weights") if root else WEIGHTS
    processed_dir = (root / "data/processed") if root else PROCESSED
    manifests_dir = (root / "data/manifests") if root else MANIFESTS
    for directory in (cache, geometry_dir, weights_dir, processed_dir, manifests_dir):
        directory.mkdir(parents=True, exist_ok=True)

    ens, hres, cloud_report = open_mean_sources_and_validate()
    valid = init + np.timedelta64(lead_hours, "h")
    earlier_init = init - np.timedelta64(12, "h")
    earlier_lead = lead_hours + 12
    available_leads = set(lead_hours_values(ens))
    if earlier_lead not in available_leads:
        raise ValidationError(f"No earlier-cycle lead {earlier_lead}h for run-to-run drift")

    forecast = select_india(ens[FORECAST_VARIABLES].sel(time=init, prediction_timedelta=lead_selector(ens, lead_hours))).load()
    previous_mslp = select_india(
        ens[["mean_sea_level_pressure"]].sel(time=earlier_init, prediction_timedelta=lead_selector(ens, earlier_lead))
    )["mean_sea_level_pressure"].load()
    analysis_state_raw = select_india(hres[ANALYSIS_STATE_VARIABLES].sel(time=valid)).load()
    precip_times = valid - np.asarray([18, 12, 6, 0], dtype="timedelta64[h]")
    analysis_precip_raw = select_india(hres[["total_precipitation_6hr"]].sel(time=precip_times)).load()
    if analysis_precip_raw.sizes.get("time") != 4:
        raise ValidationError("Expected four 6-hour HRES precipitation periods for a 24-hour total")

    analysis_state, state_alignment = align_to_target(
        analysis_state_raw, forecast, ANALYSIS_STATE_VARIABLES, "bilinear", weights_dir / "regridding"
    )
    precip_total = analysis_precip_raw["total_precipitation_6hr"].sum("time", keep_attrs=True).to_dataset(name="total_precipitation_24hr")
    precip_total["total_precipitation_24hr"].attrs["units"] = "m"
    aligned_precip, precip_alignment = align_to_target(
        precip_total, forecast, ["total_precipitation_24hr"], "conservative", weights_dir / "regridding"
    )
    analysis_precip24_mm = precipitation_to_mm(aligned_precip["total_precipitation_24hr"])

    source_shp, source_hashes = acquire_geometry(cache / "Indian_met_zones")
    canonical_path = geometry_dir / "imd_subdivisions.geojson"
    geometry_report_path = geometry_dir / "geometry_validation.json"
    regions, geometry_report = validate_and_canonicalize_geometry(
        source_shp, canonical_path, geometry_report_path, load_expected_manifest(geometry_dir / "expected_regions.json"), allow_make_valid=True
    )
    region_weights = compute_region_weights(regions, forecast.latitude.values, forecast.longitude.values)
    region_weights_path = weights_dir / "region_weights.parquet"
    region_weights.write_parquet(region_weights_path)

    features = build_forecast_feature_rows(forecast, previous_mslp, region_weights, init, lead_hours)
    errors = build_verification_error_rows(forecast, analysis_state, analysis_precip24_mm, region_weights)
    rows = compose_derived_rows(features, errors)
    if rows.height != 36:
        raise ValidationError(f"Derived row count={rows.height}; expected one row per 36 subdivisions")

    partition_dir = processed_dir / f"year={str(init)[:4]}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = partition_dir / f"smoke-init={str(init)[:13].replace(':','')}-lead={lead_hours:03d}.parquet"
    rows.write_parquet(parquet_path)
    manifest = build_manifest(
        parquet_path,
        rows,
        cloud_report,
        geometry_report,
        source_hashes,
        [state_alignment, precip_alignment],
        region_weights_path,
    )
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["geometry_validation_report"] = str(geometry_report_path)
    manifest["geometry_validation_report_sha256"] = sha256_file(geometry_report_path)
    manifest_path = manifests_dir / "smoke-dataset-manifest.json"
    write_manifest(manifest_path, manifest)
    return {
        "parquet": str(parquet_path),
        "manifest": str(manifest_path),
        "rows": rows.height,
        "region_weights": str(region_weights_path),
        "geometry": str(canonical_path),
        "confirmed_ens_variables": cloud_report["ens_mean_variables"],
        "confirmed_hres_variables": cloud_report["hres_variables"],
    }
