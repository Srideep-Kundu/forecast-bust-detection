from __future__ import annotations

import gc
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from .constants import (
    ARTIFACTS,
    CACHE,
    DATASET_VERSION,
    FEATURE_CONTRACT_VERSION,
    GEOMETRY,
    LEAD_HOURS,
    MANIFESTS,
    MONSOON_MONTHS,
    PROCESSED,
    WEIGHTS,
    WEATHERBENCH_CACHE,
    ENS_MEAN_URL,
    ENS_URL,
    HRES_URL,
)
from .acquisition import fetch_cycle_source_slices, load_cycle_source_slices_from_cache
from .exceptions import ValidationError
from .features import build_forecast_feature_rows, build_verification_error_rows, precipitation_to_mm
from .features import FEATURE_COLUMNS
from .geometry import acquire_geometry, compute_region_weights, load_expected_manifest, validate_and_canonicalize_geometry
from .hashing import sha256_file, sha256_json
from .pipeline import ANALYSIS_STATE_VARIABLES, FORECAST_VARIABLES, compose_derived_rows
from .regrid import align_to_target
from .weatherbench import lead_hours_values, lead_selector, open_and_validate, open_mean_sources_and_validate, open_sources_and_validate, select_india


ROWS_PER_CYCLE = 36 * len(LEAD_HOURS)


def _atomic_parquet(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.write_parquet(temporary)
    os.replace(temporary, path)


def _atomic_json(path: Path, value: dict) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def expected_initializations(ens) -> list[np.datetime64]:
    values = np.asarray(ens.time.values).astype("datetime64[ns]")
    selected = [value for value in values if int(str(value)[5:7]) in MONSOON_MONTHS and 2018 <= int(str(value)[:4]) <= 2022]
    bad_hours = [str(value) for value in selected if int(str(value)[11:13]) not in (0, 12)]
    if bad_hours:
        raise ValidationError(f"Unexpected initialization hours: {bad_hours[:5]}")
    return selected


def _cycle_path(processed: Path, initialization: np.datetime64) -> Path:
    stamp = str(initialization.astype("datetime64[h]")).replace(":", "")
    return processed / f"year={stamp[:4]}" / f"month={stamp[5:7]}" / f"init={stamp}.parquet"


def _valid_cycle_file(path: Path, initialization: np.datetime64, expected_hash: str | None = None) -> bool:
    if not path.exists():
        return False
    try:
        if expected_hash is not None and sha256_file(path) != expected_hash:
            return False
        frame = pl.read_parquet(path)
        return (
            frame.height == ROWS_PER_CYCLE
            and frame["forecast_initialization_time"].n_unique() == 1
            and frame["forecast_initialization_time"][0].startswith(str(initialization.astype("datetime64[h]")))
            and sorted(frame["lead_day"].unique().to_list()) == list(range(1, 11))
            and frame["region_id"].n_unique() == 36
            and set(FEATURE_COLUMNS).issubset(frame.columns)
            and not any("spread" in name for name in frame.columns)
            and frame["dataset_version"].n_unique() == 1
            and frame["dataset_version"][0] == DATASET_VERSION
        )
    except Exception:
        return False


def _prepare_regions(root: Path | None, ens):
    cache = root / "data/cache" if root else CACHE
    geometry_dir = root / "data/geometry" if root else GEOMETRY
    weights_dir = root / "data/weights" if root else WEIGHTS
    for directory in (cache, geometry_dir, weights_dir):
        directory.mkdir(parents=True, exist_ok=True)
    source, source_hashes = acquire_geometry(cache / "Indian_met_zones")
    canonical = geometry_dir / "imd_subdivisions.geojson"
    report_path = geometry_dir / "geometry_validation.json"
    regions, geometry_report = validate_and_canonicalize_geometry(
        source,
        canonical,
        report_path,
        load_expected_manifest(geometry_dir / "expected_regions.json"),
        allow_make_valid=True,
    )
    target = select_india(ens)
    weights = compute_region_weights(regions, target.latitude.values, target.longitude.values)
    weights_path = weights_dir / "region_weights.parquet"
    _atomic_parquet(weights, weights_path)
    return weights, weights_path, source_hashes, geometry_report, weights_dir


def derive_cycle_rows(
    forecast,
    previous,
    analysis_state_raw,
    analysis_precip_raw,
    weights: pl.DataFrame,
    weights_dir: Path,
    initialization: np.datetime64,
) -> tuple[pl.DataFrame, list[dict]]:
    valid_times = initialization + np.asarray(LEAD_HOURS, dtype="timedelta64[h]")
    analysis_state, state_alignment = align_to_target(
        analysis_state_raw, forecast, ANALYSIS_STATE_VARIABLES, "bilinear", weights_dir / "regridding"
    )
    analysis_precip, precip_alignment = align_to_target(
        analysis_precip_raw, forecast, ["total_precipitation_6hr"], "conservative", weights_dir / "regridding"
    )

    frames = []
    for lead, valid in zip(LEAD_HOURS, valid_times, strict=True):
        forecast_lead = forecast.sel(prediction_timedelta=lead_selector(forecast, lead))
        previous_lead = previous.sel(prediction_timedelta=lead_selector(previous.to_dataset(name="mean_sea_level_pressure"), lead + 12))
        state = analysis_state.sel(time=valid)
        window = valid - np.asarray([18, 12, 6, 0], dtype="timedelta64[h]")
        precip = analysis_precip["total_precipitation_6hr"].sel(time=window).sum("time", keep_attrs=True)
        precip.attrs["units"] = "m"
        precip_mm = precipitation_to_mm(precip)
        features = build_forecast_feature_rows(forecast_lead, previous_lead, weights, initialization, lead)
        errors = build_verification_error_rows(forecast_lead, state, precip_mm, weights)
        frames.append(compose_derived_rows(features, errors))
    result = pl.concat(frames, how="vertical").sort(["lead_day", "region_id"])
    if result.height != ROWS_PER_CYCLE:
        raise ValidationError(f"Cycle produced {result.height} rows; expected {ROWS_PER_CYCLE}")
    return result, [state_alignment, precip_alignment]


def build_cycle_rows(
    ens,
    ens_mean,
    hres,
    weights: pl.DataFrame,
    weights_dir: Path,
    initialization: np.datetime64,
    cache_root: Path = WEATHERBENCH_CACHE,
    concurrency: int = 1,
    cache_only: bool = False,
) -> tuple[pl.DataFrame, list[dict]]:
    available = set(lead_hours_values(ens_mean))
    missing = sorted(set(value + 12 for value in LEAD_HOURS) - available)
    if missing:
        raise ValidationError(f"Missing same-valid-time earlier-cycle leads: {missing}")
    forecast, previous, analysis_state, analysis_precip, _ = fetch_cycle_source_slices(
        ens,
        ens_mean,
        hres,
        initialization,
        cache_root=cache_root,
        concurrency=concurrency,
        cache_only=cache_only,
    )
    return derive_cycle_rows(forecast, previous, analysis_state, analysis_precip, weights, weights_dir, initialization)


def fetch_source_slices(initialization: str, concurrency: int = 1, root: Path | None = None) -> dict:
    ens_mean, hres, _ = open_mean_sources_and_validate()
    cache_root = root / "data/cache/weatherbench" if root else WEATHERBENCH_CACHE
    init = np.datetime64(initialization, "ns")
    _, _, _, _, stats = fetch_cycle_source_slices(None, ens_mean, hres, init, cache_root=cache_root, concurrency=concurrency)
    return {"initialization": str(init), "cache_hits": stats.cache_hits, "cache_misses": stats.cache_misses, "artifacts": stats.artifacts}


def build_derived(initialization: str, concurrency: int = 1, root: Path | None = None) -> dict:
    init = np.datetime64(initialization, "ns")
    cache_root = root / "data/cache/weatherbench" if root else WEATHERBENCH_CACHE
    weights_dir = root / "data/weights" if root else WEIGHTS
    weights_path = weights_dir / "region_weights.parquet"
    if not weights_path.exists():
        raise ValidationError(
            f"Validated region weights are required before cache-only derivation: {weights_path}"
        )
    weights = pl.read_parquet(weights_path)
    if weights["region_id"].n_unique() != 36:
        raise ValidationError(f"Region weights contain {weights['region_id'].n_unique()} regions; expected 36")
    forecast, previous, analysis_state, analysis_precip, _ = load_cycle_source_slices_from_cache(init, cache_root)
    rows, alignments = derive_cycle_rows(
        forecast,
        previous,
        analysis_state,
        analysis_precip,
        weights,
        weights_dir,
        init,
    )
    processed = root / "data/processed" if root else PROCESSED
    output = _cycle_path(processed, init)
    _atomic_parquet(rows, output)
    return {"initialization": str(init), "rows": rows.height, "parquet": str(output), "sha256": sha256_file(output), "alignments": alignments}


def _corpus_manifest(
    paths: list[Path],
    expected: list[np.datetime64],
    cloud_report: dict,
    weights_path: Path,
    source_hashes: dict,
    geometry_report: dict,
    alignments: list[dict],
) -> dict:
    by_stamp = {path.stem.removeprefix("init="): path for path in paths}
    expected_stamps = [str(value.astype("datetime64[h]")).replace(":", "") for value in expected]
    missing = [stamp for stamp in expected_stamps if stamp not in by_stamp]
    unexpected = sorted(set(by_stamp) - set(expected_stamps))
    partitions = [
        {"path": str(path), "sha256": sha256_file(path), "rows": pl.scan_parquet(path).select(pl.len()).collect().item()}
        for path in sorted(paths)
    ]
    return {
        "dataset_version": DATASET_VERSION,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "spread_scope_decision": {
            "raw_member_access": False,
            "reason": "Deferred from the four-day MVP because WeatherBench member chunks make acquisition impractical.",
            "benchmark": {"full_spread_projected_bytes": 1151249040212, "precipitation_spread_projected_bytes": 350432288542, "mean_only_projected_bytes": 74454723362},
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if not missing and not unexpected and sum(item["rows"] for item in partitions) == len(expected) * ROWS_PER_CYCLE else "incomplete",
        "expected_initialization_count": len(expected),
        "completed_initialization_count": len(paths),
        "expected_row_count": len(expected) * ROWS_PER_CYCLE,
        "row_count": sum(item["rows"] for item in partitions),
        "missing_initializations": missing,
        "unexpected_initializations": unexpected,
        "coverage": {"years": [2018, 2019, 2020, 2021, 2022], "months": list(MONSOON_MONTHS), "lead_hours": list(LEAD_HOURS)},
        "dimensions": cloud_report,
        "sources": {
            "ifs_ens_mean_for_deterministic_fields": ENS_MEAN_URL,
            "raw_ensemble_member_access": False,
            "ifs_hres_t0_verification": HRES_URL,
        },
        "region_definition": geometry_report,
        "grids": alignments,
        "partitions": partitions,
        "hashes": {
            "manifest_content_sha256": sha256_json(partitions),
            "geometry_source_files": source_hashes,
            "region_weights_sha256": sha256_file(weights_path),
        },
        "licensing": {
            "raw_weatherbench_tigge_redistribution": "disabled",
            "derived_redistribution": "disabled pending license confirmation",
            "attribution_required": True,
        },
    }


def build_full_corpus(root: Path | None = None, max_cycles: int | None = None, concurrency: int = 1) -> dict:
    if max_cycles is not None and max_cycles < 0:
        raise ValidationError("max_cycles must be non-negative")
    processed = root / "data/processed" if root else PROCESSED
    manifests = root / "data/manifests" if root else MANIFESTS
    artifacts = root / "data/artifacts" if root else ARTIFACTS
    for directory in (processed, manifests, artifacts):
        directory.mkdir(parents=True, exist_ok=True)
    ens_mean, hres, cloud_report = open_mean_sources_and_validate()
    expected = expected_initializations(ens_mean)
    weights, weights_path, source_hashes, geometry_report, weights_dir = _prepare_regions(root, ens_mean)
    completed_this_run = 0
    alignments: list[dict] = []
    started = time.monotonic()
    manifest_path = manifests / "full-dataset-manifest.json"
    prior_hashes: dict[str, str] = {}
    if manifest_path.exists():
        import json

        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        prior_hashes = {str(item["path"]): str(item["sha256"]) for item in prior.get("partitions", [])}
    try:
        for index, initialization in enumerate(expected, start=1):
            if max_cycles == 0:
                break
            output = _cycle_path(processed, initialization)
            if _valid_cycle_file(output, initialization, prior_hashes.get(str(output))):
                continue
            if output.exists():
                quarantine = output.with_suffix(output.suffix + f".invalid-{int(time.time())}")
                os.replace(output, quarantine)
            cache_root = root / "data/cache/weatherbench" if root else WEATHERBENCH_CACHE
            rows, alignments = build_cycle_rows(None, ens_mean, hres, weights, weights_dir, initialization, cache_root, concurrency)
            _atomic_parquet(rows, output)
            completed_this_run += 1
            gc.collect()
            print(f"[{index}/{len(expected)}] wrote {output} ({rows.height} rows)", flush=True)
            if max_cycles is not None and completed_this_run >= max_cycles:
                break
    finally:
        # A Ctrl-C or network failure never commits a partial Parquet file, but it
        # still leaves an exact checkpoint manifest for the next invocation.
        paths = sorted(processed.glob("year=*/month=*/init=*.parquet"))
        manifest = _corpus_manifest(paths, expected, cloud_report, weights_path, source_hashes, geometry_report, alignments)
        manifest["elapsed_seconds_this_run"] = round(time.monotonic() - started, 3)
        _atomic_json(manifest_path, manifest)
    return {
        "manifest": str(manifest_path),
        "status": manifest["status"],
        "row_count": manifest["row_count"],
        "completed_initializations": manifest["completed_initialization_count"],
        "expected_initializations": manifest["expected_initialization_count"],
        "missing_initializations": len(manifest["missing_initializations"]),
    }
