from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

import gcsfs
import numpy as np

from .constants import DIAGNOSTICS, ENS_MEAN_URL, ENS_URL, HRES_URL, LEAD_HOURS
from .weatherbench import lead_hours_values, open_sources_and_validate


ALL_MEAN_VARIABLES = (
    "mean_sea_level_pressure", "2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind",
    "total_precipitation_24hr", "u_component_of_wind", "v_component_of_wind", "geopotential",
)
RAW_SPREAD_VARIABLES = (
    "mean_sea_level_pressure", "10m_u_component_of_wind", "10m_v_component_of_wind", "total_precipitation_24hr",
)
HRES_STATE_VARIABLES = ("mean_sea_level_pressure", "2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind")


def _chunk_path(url: str, variable: str, indices: tuple[int, ...]) -> str:
    return f"{url.removeprefix('gs://')}/{variable}/" + ".".join(str(index) for index in indices)


def assess_source_layout(initialization: str = "2020-06-01T00:00:00", root: Path | None = None) -> dict:
    ens, ens_mean, hres, _ = open_sources_and_validate()
    init = np.datetime64(initialization, "ns")
    time_index = int(np.flatnonzero(ens.time.values.astype("datetime64[ns]") == init)[0])
    previous_index = int(np.flatnonzero(ens.time.values.astype("datetime64[ns]") == init - np.timedelta64(12, "h"))[0])
    leads = lead_hours_values(ens)
    lead_chunk_size = int(ens["mean_sea_level_pressure"].encoding["chunks"][2])
    lead_chunks = sorted({leads.index(value) // lead_chunk_size for value in LEAD_HOURS})
    previous_chunks = sorted({leads.index(value + 12) // lead_chunk_size for value in LEAD_HOURS})
    valid_times = init + np.asarray(LEAD_HOURS, dtype="timedelta64[h]")
    precip_times = np.unique(np.concatenate([value - np.asarray([18, 12, 6, 0], dtype="timedelta64[h]") for value in valid_times]))
    hres_lookup = {np.datetime64(value, "ns"): index for index, value in enumerate(hres.time.values)}

    old_paths: set[str] = set()
    new_paths: set[str] = set()
    path_identity: dict[str, tuple[str, str]] = {}
    for variable in ALL_MEAN_VARIABLES:
        pressure = "level" in ens[variable].dims
        for chunk in lead_chunks:
            indices = (time_index, 0, chunk, 0, 0, 0) if pressure else (time_index, 0, chunk, 0, 0)
            path = _chunk_path(ENS_URL, variable, indices)
            old_paths.add(path)
            path_identity[path] = ("ifs_ens", variable)
    for chunk in previous_chunks:
        path = _chunk_path(ENS_URL, "mean_sea_level_pressure", (previous_index, 0, chunk, 0, 0))
        old_paths.add(path)
        path_identity[path] = ("ifs_ens", "mean_sea_level_pressure")

    for variable in RAW_SPREAD_VARIABLES:
        for chunk in lead_chunks:
            path = _chunk_path(ENS_URL, variable, (time_index, 0, chunk, 0, 0))
            new_paths.add(path)
            path_identity[path] = ("ifs_ens", variable)
    for variable in ALL_MEAN_VARIABLES:
        pressure = "level" in ens_mean[variable].dims
        for chunk in lead_chunks:
            indices = (time_index, chunk, 0, 0, 0) if pressure else (time_index, chunk, 0, 0)
            path = _chunk_path(ENS_MEAN_URL, variable, indices)
            new_paths.add(path)
            path_identity[path] = ("ifs_ens_mean", variable)
    for chunk in previous_chunks:
        path = _chunk_path(ENS_MEAN_URL, "mean_sea_level_pressure", (previous_index, chunk, 0, 0))
        new_paths.add(path)
        path_identity[path] = ("ifs_ens_mean", "mean_sea_level_pressure")

    for variable in HRES_STATE_VARIABLES:
        size = int(hres[variable].encoding["chunks"][0])
        chunks = sorted({hres_lookup[np.datetime64(value, "ns")] // size for value in valid_times})
        for chunk in chunks:
            path = _chunk_path(HRES_URL, variable, (chunk, 0, 0))
            old_paths.add(path); new_paths.add(path); path_identity[path] = ("ifs_hres_t0", variable)
    precip_size = int(hres["total_precipitation_6hr"].encoding["chunks"][0])
    for chunk in sorted({hres_lookup[np.datetime64(value, "ns")] // precip_size for value in precip_times}):
        path = _chunk_path(HRES_URL, "total_precipitation_6hr", (chunk, 0, 0))
        old_paths.add(path); new_paths.add(path); path_identity[path] = ("ifs_hres_t0", "total_precipitation_6hr")

    filesystem = gcsfs.GCSFileSystem(token="anon", skip_instance_cache=True)
    sizes = {path: int(filesystem.info(path)["size"]) for path in sorted(old_paths | new_paths)}
    samples: dict[tuple[str, str], list[int]] = defaultdict(list)
    for path, size in sizes.items():
        samples[path_identity[path]].append(size)
    averages = [{"dataset": key[0], "variable": key[1], "sample_chunks": len(values), "average_compressed_bytes": sum(values) / len(values)} for key, values in sorted(samples.items())]
    old_bytes, new_bytes = sum(sizes[path] for path in old_paths), sum(sizes[path] for path in new_paths)
    report = {
        "initialization": str(init),
        "old_full_ensemble_layout": {"objects": len(old_paths), "compressed_bytes": old_bytes},
        "new_hybrid_layout": {"objects": len(new_paths), "compressed_bytes": new_bytes},
        "compressed_bytes_avoided": old_bytes - new_bytes,
        "reduction_fraction": 1.0 - new_bytes / old_bytes,
        "chunk_size_samples": averages,
        "scientific_equivalence": "Official WeatherBench 2 IFS ENS mean on the same 240x121 grid supplies deterministic means; the full 50-member IFS ENS remains the source of all four ensemble-spread features.",
    }
    output = (root / "data/diagnostics" if root else DIAGNOSTICS) / "weatherbench-source-layout.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    report["report"] = str(output)
    return report
