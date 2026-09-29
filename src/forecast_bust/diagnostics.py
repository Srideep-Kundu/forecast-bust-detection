from __future__ import annotations

import itertools
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from .acquisition import AcquisitionStats, CountingGCSFileSystem, fetch_ens_variable, fetch_hres_variable
from .constants import DIAGNOSTICS, ENS_URL, HRES_URL, INDIA_BOUNDS, WEATHERBENCH_CACHE
from .source_cache import SourceSliceCache
from .weatherbench import lead_hours_values, open_and_validate


def _indices_for_values(coordinate: xr.DataArray, values: np.ndarray) -> list[int]:
    source = np.asarray(coordinate.values)
    output = []
    for value in values:
        matches = np.flatnonzero(source == value)
        if len(matches) != 1:
            raise ValueError(f"Cannot resolve {coordinate.name}={value}")
        output.append(int(matches[0]))
    return output


def _chunk_plan(array: xr.DataArray, selected: dict[str, list[int]]) -> tuple[int, int, list[list[int]]]:
    chunks = tuple(int(value) for value in array.encoding["chunks"])
    chunk_ids = []
    for dimension, size, chunk in zip(array.dims, array.shape, chunks, strict=True):
        indices = selected.get(dimension, list(range(size)))
        chunk_ids.append(sorted({index // chunk for index in indices}))
    combinations = list(itertools.product(*chunk_ids))
    elements = 0
    for combination in combinations:
        chunk_elements = 1
        for chunk_id, size, chunk in zip(combination, array.shape, chunks, strict=True):
            start = chunk_id * chunk
            chunk_elements *= min(chunk, size - start)
        elements += chunk_elements
    return len(combinations), elements * np.dtype(array.dtype).itemsize, [list(item) for item in combinations]


def _spatial_indices(dataset: xr.Dataset) -> tuple[list[int], list[int]]:
    latitude = np.asarray(dataset.latitude.values)
    longitude = np.asarray(dataset.longitude.values)
    lat = np.flatnonzero((latitude >= INDIA_BOUNDS["latitude_min"]) & (latitude <= INDIA_BOUNDS["latitude_max"])).tolist()
    lon = np.flatnonzero((longitude >= INDIA_BOUNDS["longitude_min"]) & (longitude <= INDIA_BOUNDS["longitude_max"])).tolist()
    return lat, lon


def _record(dataset_name: str, url: str, dataset: xr.Dataset, variable: str, selected: dict[str, list[int]], role: str) -> dict:
    array = dataset[variable]
    count, theoretical, combinations = _chunk_plan(array, selected)
    requested = {dimension: {"minimum_index": min(indices), "maximum_index": max(indices), "count": len(indices)} for dimension, indices in selected.items()}
    return {
        "dataset": dataset_name,
        "role": role,
        "variable": variable,
        "source_zarr_array": f"{url}/{variable}",
        "array_shape": list(array.shape),
        "dimensions": list(array.dims),
        "chunk_shape": list(array.encoding["chunks"]),
        "dtype": str(array.dtype),
        "requested_indices": requested,
        "india_bounds": INDIA_BOUNDS,
        "source_chunks_intersected": count,
        "source_chunk_indices": combinations,
        "theoretical_uncompressed_bytes": theoretical,
        "actual_bytes_transferred": None,
        "actual_requests": None,
    }


def build_read_plan(initialization: str = "2020-06-01T00:00:00", lead_hours: int = 24, measure: bool = False, concurrency: int = 1) -> dict:
    filesystem = CountingGCSFileSystem()
    ens, hres, _ = open_and_validate(filesystem=filesystem)
    init = np.datetime64(initialization, "ns")
    valid = init + np.timedelta64(lead_hours, "h")
    previous_init = init - np.timedelta64(12, "h")
    previous_lead = lead_hours + 12
    ens_lat, ens_lon = _spatial_indices(ens)
    hres_lat, hres_lon = _spatial_indices(hres)
    ens_time = _indices_for_values(ens.time, np.asarray([init]))
    previous_time = _indices_for_values(ens.time, np.asarray([previous_init]))
    lead_index = [lead_hours_values(ens).index(lead_hours)]
    previous_lead_index = [lead_hours_values(ens).index(previous_lead)]
    valid_index = _indices_for_values(hres.time, np.asarray([valid]))
    precip_times = valid - np.asarray([18, 12, 6, 0], dtype="timedelta64[h]")
    precip_indices = _indices_for_values(hres.time, precip_times.astype("datetime64[ns]"))
    all_members = list(range(ens.sizes["number"]))
    level_lookup = {int(value): index for index, value in enumerate(ens.level.values)}

    records = []
    for variable in ("mean_sea_level_pressure", "2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind", "total_precipitation_24hr"):
        records.append(_record("ifs_ens", ENS_URL, ens, variable, {"time": ens_time, "number": all_members, "prediction_timedelta": lead_index, "latitude": ens_lat, "longitude": ens_lon}, "current_forecast"))
    for variable, levels in (("u_component_of_wind", (850,)), ("v_component_of_wind", (850,)), ("geopotential", (500, 850))):
        records.append(_record("ifs_ens", ENS_URL, ens, variable, {"time": ens_time, "number": all_members, "prediction_timedelta": lead_index, "level": [level_lookup[level] for level in levels], "latitude": ens_lat, "longitude": ens_lon}, "current_forecast"))
    records.append(_record("ifs_ens", ENS_URL, ens, "mean_sea_level_pressure", {"time": previous_time, "number": all_members, "prediction_timedelta": previous_lead_index, "latitude": ens_lat, "longitude": ens_lon}, "same_valid_time_drift"))
    for variable in ("mean_sea_level_pressure", "2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind"):
        records.append(_record("ifs_hres_t0", HRES_URL, hres, variable, {"time": valid_index, "latitude": hres_lat, "longitude": hres_lon}, "verification_state"))
    records.append(_record("ifs_hres_t0", HRES_URL, hres, "total_precipitation_6hr", {"time": precip_indices, "latitude": hres_lat, "longitude": hres_lon}, "verification_precipitation"))

    if measure:
        cache = SourceSliceCache(WEATHERBENCH_CACHE)
        stats = AcquisitionStats()
        for record in records:
            before_bytes, before_requests = filesystem.bytes_transferred, filesystem.request_count
            variable = record["variable"]
            if record["dataset"] == "ifs_ens":
                chosen_init = previous_init if record["role"] == "same_valid_time_drift" else init
                chosen_lead = previous_lead if record["role"] == "same_valid_time_drift" else lead_hours
                levels = ()
                if variable in ("u_component_of_wind", "v_component_of_wind"):
                    levels = (850,)
                elif variable == "geopotential":
                    levels = (500, 850)
                fetch_ens_variable(ens, cache, variable, chosen_init, (chosen_lead,), levels, concurrency, 4, stats)
            else:
                times = precip_times if variable == "total_precipitation_6hr" else np.asarray([valid])
                fetch_hres_variable(hres, cache, variable, times, concurrency, 4, stats)
            record["actual_bytes_transferred"] = filesystem.bytes_transferred - before_bytes
            record["actual_requests"] = filesystem.request_count - before_requests

    theoretical_total = sum(item["theoretical_uncompressed_bytes"] for item in records)
    batching = []
    ten_lead_indices = [lead_hours_values(ens).index(value) for value in (24, 48, 72, 96, 120, 144, 168, 192, 216, 240)]
    for variable, levels in (
        ("mean_sea_level_pressure", ()),
        ("2m_temperature", ()),
        ("10m_u_component_of_wind", ()),
        ("10m_v_component_of_wind", ()),
        ("total_precipitation_24hr", ()),
        ("u_component_of_wind", (850,)),
        ("v_component_of_wind", (850,)),
        ("geopotential", (500, 850)),
    ):
        base = {"time": ens_time, "number": all_members, "latitude": ens_lat, "longitude": ens_lon}
        if levels:
            base["level"] = [level_lookup[level] for level in levels]
        batched_count, batched_bytes, _ = _chunk_plan(ens[variable], base | {"prediction_timedelta": ten_lead_indices})
        individual_bytes = sum(_chunk_plan(ens[variable], base | {"prediction_timedelta": [index]})[1] for index in ten_lead_indices)
        batching.append({"variable": variable, "batched_unique_chunks": batched_count, "batched_theoretical_bytes": batched_bytes, "individual_lead_theoretical_bytes_without_shared_chunk_cache": individual_bytes, "bytes_avoided_by_batching": individual_bytes - batched_bytes})
    actual_values = [item["actual_bytes_transferred"] for item in records]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "initialization": str(init),
        "lead_hours": lead_hours,
        "concurrency": concurrency,
        "records": records,
        "ten_lead_batching_comparison": batching,
        "totals": {
            "theoretical_uncompressed_bytes": theoretical_total,
            "actual_bytes_transferred": sum(actual_values) if all(value is not None for value in actual_values) else None,
            "actual_requests": sum(item["actual_requests"] for item in records) if measure else None,
        },
        "root_cause": "The 1.5-degree IFS ENS arrays use full-global 240x121 spatial chunks, 50 members per chunk, eight leads per chunk, and all three pressure levels per pressure chunk. An India/one-lead selection therefore intersects and transfers complete global source chunks.",
    }
    path = DIAGNOSTICS / "weatherbench-read-plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return report
