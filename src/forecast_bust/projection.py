from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from .constants import DIAGNOSTICS, LEAD_HOURS, WEATHERBENCH_CACHE
from .corpus import expected_initializations
from .weatherbench import lead_hours_values, open_sources_and_validate


ENS_VARIABLES = (
    "mean_sea_level_pressure",
    "2m_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "total_precipitation_24hr",
    "u_component_of_wind",
    "v_component_of_wind",
    "geopotential",
)
RAW_SPREAD_VARIABLES: tuple[str, ...] = ()
HRES_STATE_VARIABLES = ("mean_sea_level_pressure", "2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind")


def _averages(values: dict[tuple[str, str], list[float]]) -> dict[tuple[str, str], float]:
    return {key: sum(items) / len(items) for key, items in values.items() if items}


def project_full_corpus(root: Path | None = None) -> dict:
    diagnostics = root / "data/diagnostics" if root else DIAGNOSTICS
    cache_root = root / "data/cache/weatherbench" if root else WEATHERBENCH_CACHE
    benchmark = json.loads((diagnostics / "weatherbench-benchmark.json").read_text(encoding="utf-8"))
    source_layout = json.loads((diagnostics / "weatherbench-source-layout.json").read_text(encoding="utf-8"))
    ens, ens_mean, hres, _ = open_sources_and_validate()
    initializations = expected_initializations(ens)
    ens_time_lookup = {np.datetime64(value, "ns"): index for index, value in enumerate(ens.time.values)}
    hres_time_lookup = {np.datetime64(value, "ns"): index for index, value in enumerate(hres.time.values)}
    lead_values = lead_hours_values(ens)
    lead_chunk = int(ens["mean_sea_level_pressure"].encoding["chunks"][2])
    lead_chunks = {lead_values.index(value) // lead_chunk for value in LEAD_HOURS}
    previous_lead_chunks = {lead_values.index(value + 12) // lead_chunk for value in LEAD_HOURS}

    keys: dict[tuple[str, str], set[tuple[int, int | None]]] = defaultdict(set)
    for initialization in initializations:
        time_index = ens_time_lookup[np.datetime64(initialization, "ns")]
        for variable in RAW_SPREAD_VARIABLES:
            keys[("ifs_ens", variable)].update((time_index, chunk) for chunk in lead_chunks)
        for variable in ENS_VARIABLES:
            keys[("ifs_ens_mean", variable)].update((time_index, chunk) for chunk in lead_chunks)
        previous = np.datetime64(initialization, "ns") - np.timedelta64(12, "h")
        previous_index = ens_time_lookup[previous]
        keys[("ifs_ens_mean", "mean_sea_level_pressure")].update((previous_index, chunk) for chunk in previous_lead_chunks)
        valid_times = np.datetime64(initialization, "ns") + np.asarray(LEAD_HOURS, dtype="timedelta64[h]")
        for variable in HRES_STATE_VARIABLES:
            chunk_size = int(hres[variable].encoding["chunks"][0])
            keys[("ifs_hres_t0", variable)].update((hres_time_lookup[np.datetime64(value, "ns")] // chunk_size, None) for value in valid_times)
        precipitation_times = np.unique(np.concatenate([value - np.asarray([18, 12, 6, 0], dtype="timedelta64[h]") for value in valid_times]))
        precip_chunk = int(hres["total_precipitation_6hr"].encoding["chunks"][0])
        keys[("ifs_hres_t0", "total_precipitation_6hr")].update((hres_time_lookup[np.datetime64(value, "ns")] // precip_chunk, None) for value in precipitation_times)

    actual_average = {(item["dataset"], item["variable"]): item["average_compressed_bytes"] for item in source_layout["chunk_size_samples"]}
    datasets = {"ifs_ens": ens, "ifs_ens_mean": ens_mean, "ifs_hres_t0": hres}
    theoretical_average = {}
    for key in keys:
        array = datasets[key[0]][key[1]]
        theoretical_average[key] = float(np.prod(array.encoding["chunks"]) * np.dtype(array.dtype).itemsize)

    cache_samples: dict[tuple[str, str], list[float]] = defaultdict(list)
    for path in cache_root.rglob("*.json"):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        spec = metadata.get("spec", {})
        if spec.get("dataset") and spec.get("variable") and metadata.get("bytes"):
            cache_samples[(spec["dataset"], spec["variable"])].append(float(metadata["bytes"]))
    cache_average = _averages(cache_samples)

    details = []
    projected_transfer = projected_cache = projected_theoretical = 0.0
    for key in sorted(keys):
        count = len(keys[key])
        transfer = count * actual_average[key]
        cache_bytes = count * cache_average[key]
        theoretical = count * theoretical_average[key]
        projected_transfer += transfer
        projected_cache += cache_bytes
        projected_theoretical += theoretical
        details.append({"dataset": key[0], "variable": key[1], "unique_source_chunks": count, "projected_compressed_transfer_bytes": transfer, "projected_cache_bytes": cache_bytes, "projected_uncompressed_source_bytes": theoretical})

    old_benchmark = 2728768098 / 780.625
    mean_remote_seconds = max(0.0, benchmark["first_run"]["wall_seconds"] - benchmark["second_run"]["wall_seconds"])
    measured_mean_bytes = benchmark["first_run"]["actual_bytes_transferred"]
    mean_seconds_per_object = mean_remote_seconds / benchmark["first_run"]["cache_misses"]
    mean_objects = sum(len(value) for key, value in keys.items() if key[0] == "ifs_ens_mean")
    non_mean_transfer = sum(item["projected_compressed_transfer_bytes"] for item in details if item["dataset"] != "ifs_ens_mean")
    projected_runtime = non_mean_transfer / old_benchmark + mean_objects * mean_seconds_per_object + benchmark["second_run"]["wall_seconds"] * len(initializations)
    report = {
        "unique_chunk_projection": details,
        "totals": {
            "cycles": len(initializations),
            "unique_source_chunks": sum(len(value) for value in keys.values()),
            "projected_compressed_transfer_bytes": projected_transfer,
            "projected_uncompressed_source_bytes": projected_theoretical,
            "projected_cache_bytes": projected_cache,
            "projected_runtime_seconds": projected_runtime,
            "raw_chunk_measured_throughput_bytes_per_second": old_benchmark,
            "mean_chunk_measured_seconds_per_object": mean_seconds_per_object,
        },
        "benchmark_reconstruction": {
            "old_layout_cold_bytes": source_layout["old_full_ensemble_layout"]["compressed_bytes"],
            "optimized_layout_cold_bytes": benchmark["first_run"]["actual_bytes_transferred"],
            "optimized_cold_runtime_seconds_estimate": benchmark["first_run"]["wall_seconds"],
            "cache_only_actual_bytes": benchmark["second_run"]["actual_bytes_transferred"],
            "cache_only_seconds": benchmark["second_run"]["wall_seconds"],
            "cache_size_bytes": benchmark["cache_size_bytes"],
        },
        "practical": True,
        "decision": "Mean-only production contract accepted after a zero-raw-member cold benchmark; the restartable corpus build may proceed.",
    }
    output = diagnostics / "weatherbench-projection.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    report["report"] = str(output)
    return report
