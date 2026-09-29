from __future__ import annotations

from pathlib import Path

import polars as pl

from .constants import DATASET_VERSION, FEATURE_CONTRACT_VERSION, ENS_MEAN_URL, GEOMETRY_REPO, HRES_URL, WB2_GUIDE
from .hashing import sha256_file, write_json


def build_manifest(
    parquet_path: Path,
    rows: pl.DataFrame,
    cloud_report: dict,
    geometry_report: dict,
    geometry_source_hashes: dict,
    alignment_records: list[dict],
    region_weights_path: Path,
) -> dict:
    manifest = {
        "dataset_version": DATASET_VERSION,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "redistribution_enabled": False,
        "sources": {
            "ifs_ens_mean": ENS_MEAN_URL,
            "ifs_hres_t0": HRES_URL,
            "weatherbench_data_guide": WB2_GUIDE,
            "geometry_repository": GEOMETRY_REPO,
        },
        "coverage": {
            "sample_initialization_min": rows["forecast_initialization_time"].min(),
            "sample_initialization_max": rows["forecast_initialization_time"].max(),
            "sample_valid_time_min": rows["valid_time"].min(),
            "sample_valid_time_max": rows["valid_time"].max(),
        },
        "variables": rows.columns,
        "schema": {name: str(dtype) for name, dtype in rows.schema.items()},
        "units": {
            "mslp_mean_pa": "Pa", "mslp_gradient_pa_per_km": "Pa/km",
            "temperature2m_mean_k": "K", "u10_mean_mps": "m/s", "v10_mean_mps": "m/s", "wind10_mean_mps": "m/s",
            "wind850_mean_mps": "m/s", "vorticity850_s1": "s^-1", "thickness500_850_m": "m",
            "precip24_mean_mm": "mm", "run_to_run_mslp_drift_pa": "Pa",
            "e_precip_mm": "mm", "e_wind_mps": "m/s", "e_temperature_k": "K", "e_mslp_pa": "Pa",
        },
        "dimensions": cloud_report,
        "grids": alignment_records,
        "region_definition": geometry_report,
        "hashes": {
            "geometry_source_files": geometry_source_hashes,
            "region_weights_sha256": sha256_file(region_weights_path),
            "parquet_sha256": sha256_file(parquet_path),
        },
        "artifacts": {"parquet": str(parquet_path), "region_weights": str(region_weights_path)},
        "row_count": rows.height,
        "licensing": {
            "raw_weatherbench_tigge_redistribution": "disabled",
            "derived_redistribution": "disabled pending license confirmation",
            "attribution_required": True,
        },
        "raw_ensemble_member_access": False,
        "spread_scope_decision": "Deferred from the four-day MVP after measured projections of 1.151 TB for full spread and 350.43 GB for precipitation-only, versus 74.45 GB for the mean product.",
    }
    return manifest


def write_manifest(path: Path, manifest: dict) -> None:
    write_json(path, manifest)
