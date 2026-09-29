from __future__ import annotations

import threading
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import dask
import gcsfs
import numpy as np
import xarray as xr

from .constants import DATASET_VERSION, ENS_MEAN_URL, ENS_URL, HRES_URL, INDIA_BOUNDS, LEAD_HOURS, WEATHERBENCH_CACHE
from .exceptions import ValidationError
from .source_cache import SourceSliceCache, SourceSliceSpec, retry_transient
from .weatherbench import lead_hours_values, lead_selector, select_india


SPREAD_SOURCE_VARIABLES = {
    "precip": ("total_precipitation_24hr",),
    "temperature": ("2m_temperature",),
    "mslp": ("mean_sea_level_pressure",),
    "wind": ("10m_u_component_of_wind", "10m_v_component_of_wind"),
}
RESEARCH_SPREAD_FEATURES = ("precip", "mslp", "wind")
DEFAULT_SPREAD_FEATURES: tuple[str, ...] = ()


def normalize_spread_features(spread_features: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    selected = DEFAULT_SPREAD_FEATURES if spread_features is None else tuple(spread_features)
    unknown = sorted(set(selected) - set(SPREAD_SOURCE_VARIABLES))
    if unknown:
        raise ValidationError(f"Unknown spread features: {unknown}")
    return tuple(name for name in SPREAD_SOURCE_VARIABLES if name in selected)


class CountingGCSFileSystem(gcsfs.GCSFileSystem):
    """GCS filesystem that counts response payload bytes and object reads."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("token", "anon")
        kwargs.setdefault("skip_instance_cache", True)
        super().__init__(*args, **kwargs)
        self.bytes_transferred = 0
        self.request_count = 0
        self.bytes_by_path: dict[str, int] = {}
        self._counter_lock = threading.Lock()

    async def _cat_file(self, path, start=None, end=None, mrd=None, **kwargs):
        result = await super()._cat_file(path, start=start, end=end, mrd=mrd, **kwargs)
        size = len(result)
        with self._counter_lock:
            self.bytes_transferred += size
            self.request_count += 1
            self.bytes_by_path[path] = self.bytes_by_path.get(path, 0) + size
        return result


@dataclass
class AcquisitionStats:
    cache_hits: int = 0
    cache_misses: int = 0
    artifacts: list[dict] = field(default_factory=list)


def _chunk_size(array: xr.DataArray, dimension: str) -> int:
    chunks = array.encoding.get("chunks")
    if not chunks:
        raise ValidationError(f"{array.name} has no persisted Zarr chunk metadata")
    return int(chunks[array.dims.index(dimension)])


def _coordinate_indices(coordinate: xr.DataArray, selected_values: np.ndarray) -> list[int]:
    lookup = {value.item() if hasattr(value, "item") else value: index for index, value in enumerate(coordinate.values)}
    indices = []
    for value in selected_values:
        key = value.item() if hasattr(value, "item") else value
        if key not in lookup:
            raise ValidationError(f"Coordinate value {value!r} not present in {coordinate.name}")
        indices.append(lookup[key])
    return indices


def _time_index(dataset: xr.Dataset, value: np.datetime64) -> int:
    matches = np.flatnonzero(np.asarray(dataset.time.values).astype("datetime64[ns]") == np.datetime64(value, "ns"))
    if len(matches) != 1:
        raise ValidationError(f"Expected one source time for {value}; found {len(matches)}")
    return int(matches[0])


def _spec(dataset: str, variable: str, time_chunk: int, lead_chunk: int | None, levels: tuple[int, ...]) -> SourceSliceSpec:
    source_urls = {"ifs_ens": ENS_URL, "ifs_ens_mean": ENS_MEAN_URL, "ifs_hres_t0": HRES_URL}
    return SourceSliceSpec(
        source_url=source_urls[dataset],
        source_version=DATASET_VERSION,
        dataset=dataset,
        variable=variable,
        time_chunk=time_chunk,
        lead_chunk=lead_chunk,
        levels_hpa=levels,
        spatial_bounds=(
            INDIA_BOUNDS["latitude_min"],
            INDIA_BOUNDS["latitude_max"],
            INDIA_BOUNDS["longitude_min"],
            INDIA_BOUNDS["longitude_max"],
        ),
    )


def _cached_piece(
    cache: SourceSliceCache,
    spec: SourceSliceSpec,
    loader,
    stats: AcquisitionStats,
    attempts: int,
    cache_only: bool = False,
) -> xr.Dataset:
    if cache_only:
        dataset = cache.read(spec)
        if dataset is None:
            raise ValidationError(f"Required source cache artifact is missing for {spec.dataset}/{spec.variable}")
        hit = True
    else:
        dataset, hit = cache.get_or_fetch(
            spec,
            loader,
            lambda operation, label: retry_transient(operation, label, attempts=attempts),
        )
    stats.cache_hits += int(hit)
    stats.cache_misses += int(not hit)
    data_path, metadata_path = cache.paths(spec)
    stats.artifacts.append({"data": str(data_path), "metadata": str(metadata_path), "cache_hit": hit})
    return dataset


def fetch_ens_variable(
    ens: xr.Dataset | None,
    cache: SourceSliceCache,
    variable: str,
    initialization: np.datetime64,
    requested_leads: tuple[int, ...],
    levels: tuple[int, ...] = (),
    concurrency: int = 1,
    attempts: int = 4,
    stats: AcquisitionStats | None = None,
    cache_only: bool = False,
    dataset_name: str = "ifs_ens",
) -> xr.DataArray:
    stats = stats or AcquisitionStats()
    array = ens[variable]
    time_index = _time_index(ens, initialization)
    time_chunk_size = _chunk_size(array, "time")
    lead_chunk_size = _chunk_size(array, "prediction_timedelta")
    source_leads = lead_hours_values(ens)
    requested_indices = [source_leads.index(value) for value in requested_leads]
    lead_chunks = sorted({index // lead_chunk_size for index in requested_indices})
    def load_chunk(lead_chunk: int):
        start, stop = lead_chunk * lead_chunk_size, min((lead_chunk + 1) * lead_chunk_size, len(source_leads))
        spec = _spec(dataset_name, variable, time_index // time_chunk_size, lead_chunk, levels)

        def loader():
            selected = ens[[variable]].isel(
                time=slice(time_index, time_index + 1), prediction_timedelta=slice(start, stop)
            )
            if levels:
                selected = selected.sel(level=list(levels))
            selected = select_india(selected)
            with dask.config.set(scheduler="synchronous"):
                return selected.load()

        return _cached_piece(cache, spec, loader, stats, attempts, cache_only)

    if concurrency == 1 or len(lead_chunks) == 1:
        pieces = [load_chunk(chunk) for chunk in lead_chunks]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            pieces = list(executor.map(load_chunk, lead_chunks))
    combined = xr.concat(pieces, dim="prediction_timedelta").sortby("prediction_timedelta")
    selected = combined.sel(
        time=np.datetime64(initialization, "ns"),
        prediction_timedelta=lead_selector(combined, requested_leads),
    )
    return selected[variable]


def fetch_hres_variable(
    hres: xr.Dataset,
    cache: SourceSliceCache,
    variable: str,
    requested_times: np.ndarray,
    concurrency: int = 1,
    attempts: int = 4,
    stats: AcquisitionStats | None = None,
    cache_only: bool = False,
) -> xr.DataArray:
    stats = stats or AcquisitionStats()
    array = hres[variable]
    time_chunk_size = _chunk_size(array, "time")
    indices = _coordinate_indices(hres.time, np.asarray(requested_times).astype("datetime64[ns]"))
    time_chunks = sorted({index // time_chunk_size for index in indices})
    def load_chunk(time_chunk: int):
        start, stop = time_chunk * time_chunk_size, min((time_chunk + 1) * time_chunk_size, hres.sizes["time"])
        spec = _spec("ifs_hres_t0", variable, time_chunk, None, ())

        def loader():
            selected = select_india(hres[[variable]].isel(time=slice(start, stop)))
            with dask.config.set(scheduler="synchronous"):
                return selected.load()

        return _cached_piece(cache, spec, loader, stats, attempts, cache_only)

    if concurrency == 1 or len(time_chunks) == 1:
        pieces = [load_chunk(chunk) for chunk in time_chunks]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            pieces = list(executor.map(load_chunk, time_chunks))
    combined = xr.concat(pieces, dim="time").sortby("time")
    return combined[variable].sel(time=requested_times)


def fetch_cycle_source_slices(
    ens: xr.Dataset,
    ens_mean: xr.Dataset,
    hres: xr.Dataset,
    initialization: np.datetime64,
    cache_root: Path = WEATHERBENCH_CACHE,
    concurrency: int = 1,
    attempts: int = 4,
    cache_only: bool = False,
    spread_features: tuple[str, ...] | list[str] | None = None,
) -> tuple[xr.Dataset, xr.DataArray, xr.Dataset, xr.Dataset, AcquisitionStats]:
    if concurrency not in (1, 2, 4):
        raise ValidationError("concurrency must be one of 1, 2, or 4")
    cache = SourceSliceCache(cache_root)
    stats = AcquisitionStats()
    current_leads = tuple(LEAD_HOURS)
    previous_leads = tuple(value + 12 for value in LEAD_HOURS)
    previous_initialization = initialization - np.timedelta64(12, "h")
    valid_times = initialization + np.asarray(LEAD_HOURS, dtype="timedelta64[h]")
    precipitation_times = np.unique(
        np.concatenate([valid - np.asarray([18, 12, 6, 0], dtype="timedelta64[h]") for valid in valid_times])
    )

    fields = {
        "mean_sea_level_pressure": fetch_ens_variable(ens_mean, cache, "mean_sea_level_pressure", initialization, current_leads, concurrency=concurrency, attempts=attempts, stats=stats, cache_only=cache_only, dataset_name="ifs_ens_mean"),
        "2m_temperature": fetch_ens_variable(ens_mean, cache, "2m_temperature", initialization, current_leads, concurrency=concurrency, attempts=attempts, stats=stats, cache_only=cache_only, dataset_name="ifs_ens_mean"),
        "10m_u_component_of_wind": fetch_ens_variable(ens_mean, cache, "10m_u_component_of_wind", initialization, current_leads, concurrency=concurrency, attempts=attempts, stats=stats, cache_only=cache_only, dataset_name="ifs_ens_mean"),
        "10m_v_component_of_wind": fetch_ens_variable(ens_mean, cache, "10m_v_component_of_wind", initialization, current_leads, concurrency=concurrency, attempts=attempts, stats=stats, cache_only=cache_only, dataset_name="ifs_ens_mean"),
        "total_precipitation_24hr": fetch_ens_variable(ens_mean, cache, "total_precipitation_24hr", initialization, current_leads, concurrency=concurrency, attempts=attempts, stats=stats, cache_only=cache_only, dataset_name="ifs_ens_mean"),
        "u_component_of_wind": fetch_ens_variable(ens_mean, cache, "u_component_of_wind", initialization, current_leads, (850,), concurrency, attempts, stats, cache_only, "ifs_ens_mean"),
        "v_component_of_wind": fetch_ens_variable(ens_mean, cache, "v_component_of_wind", initialization, current_leads, (850,), concurrency, attempts, stats, cache_only, "ifs_ens_mean"),
        "geopotential": fetch_ens_variable(ens_mean, cache, "geopotential", initialization, current_leads, (500, 850), concurrency, attempts, stats, cache_only, "ifs_ens_mean"),
    }
    selected_spreads = normalize_spread_features(spread_features)
    if selected_spreads and ens is None:
        raise ValidationError("Research spread mode requires the full-member IFS ENS source")
    spread_variables = tuple(dict.fromkeys(variable for feature in selected_spreads for variable in SPREAD_SOURCE_VARIABLES[feature]))
    for variable in spread_variables:
        raw = fetch_ens_variable(ens, cache, variable, initialization, current_leads, concurrency=concurrency, attempts=attempts, stats=stats, cache_only=cache_only)
        fields[f"{variable}_spread"] = raw.std("number")
    forecast = xr.Dataset(fields)
    previous_mslp = fetch_ens_variable(
        ens_mean, cache, "mean_sea_level_pressure", previous_initialization, previous_leads, concurrency=concurrency, attempts=attempts, stats=stats, cache_only=cache_only, dataset_name="ifs_ens_mean"
    )
    analysis_state = xr.Dataset(
        {
            variable: fetch_hres_variable(hres, cache, variable, valid_times, concurrency, attempts, stats, cache_only)
            for variable in ("mean_sea_level_pressure", "2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind")
        }
    )
    analysis_precip = fetch_hres_variable(
        hres, cache, "total_precipitation_6hr", precipitation_times, concurrency, attempts, stats, cache_only
    ).to_dataset(name="total_precipitation_6hr")
    return forecast, previous_mslp, analysis_state, analysis_precip, stats


def _spec_from_metadata(metadata: dict) -> SourceSliceSpec:
    value = dict(metadata["spec"])
    value["levels_hpa"] = tuple(value["levels_hpa"])
    value["spatial_bounds"] = tuple(value["spatial_bounds"])
    return SourceSliceSpec(**value)


def _load_cached_variable(
    cache: SourceSliceCache,
    dataset_name: str,
    variable: str,
    requested_times: np.ndarray,
    requested_leads: tuple[int, ...] | None = None,
) -> xr.DataArray:
    directory = cache.root / dataset_name / variable
    pieces = []
    requested_time_set = {str(np.datetime64(value, "ns")) for value in np.atleast_1d(requested_times)}
    for metadata_path in sorted(directory.glob("*.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source_times = {str(np.datetime64(value, "ns")) for value in metadata.get("source_times", [])}
        if not source_times & requested_time_set:
            continue
        if requested_leads is not None and not set(metadata.get("prediction_timedelta_hours", [])) & set(requested_leads):
            continue
        dataset = cache.read(_spec_from_metadata(metadata))
        if dataset is None:
            continue
        pieces.append(dataset)
    if not pieces:
        raise ValidationError(f"No verified cache artifacts for {dataset_name}/{variable} at {sorted(requested_time_set)}")
    dimension = "prediction_timedelta" if requested_leads is not None else "time"
    combined = xr.concat(pieces, dim=dimension).sortby(dimension)
    _, unique_indices = np.unique(combined[dimension].values, return_index=True)
    combined = combined.isel({dimension: np.sort(unique_indices)})
    selected = combined.sel(time=requested_times)
    if requested_leads is not None:
        selected = selected.sel(prediction_timedelta=lead_selector(selected, requested_leads))
    return selected[variable].squeeze("time", drop=True) if np.atleast_1d(requested_times).size == 1 else selected[variable]


def load_cycle_source_slices_from_cache(
    initialization: np.datetime64,
    cache_root: Path = WEATHERBENCH_CACHE,
    spread_features: tuple[str, ...] | list[str] | None = None,
) -> tuple[xr.Dataset, xr.DataArray, xr.Dataset, xr.Dataset, AcquisitionStats]:
    cache = SourceSliceCache(cache_root)
    stats = AcquisitionStats()
    current_leads = tuple(LEAD_HOURS)
    previous_leads = tuple(value + 12 for value in LEAD_HOURS)
    previous_initialization = initialization - np.timedelta64(12, "h")
    valid_times = initialization + np.asarray(LEAD_HOURS, dtype="timedelta64[h]")
    precipitation_times = np.unique(np.concatenate([valid - np.asarray([18, 12, 6, 0], dtype="timedelta64[h]") for valid in valid_times]))
    fields = {
        variable: _load_cached_variable(cache, "ifs_ens_mean", variable, np.asarray([initialization]), current_leads)
        for variable in ("mean_sea_level_pressure", "2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind", "total_precipitation_24hr", "u_component_of_wind", "v_component_of_wind", "geopotential")
    }
    selected_spreads = normalize_spread_features(spread_features)
    spread_variables = tuple(dict.fromkeys(variable for feature in selected_spreads for variable in SPREAD_SOURCE_VARIABLES[feature]))
    for variable in spread_variables:
        raw = _load_cached_variable(cache, "ifs_ens", variable, np.asarray([initialization]), current_leads)
        fields[f"{variable}_spread"] = raw.std("number")
    forecast = xr.Dataset(fields)
    previous = _load_cached_variable(cache, "ifs_ens_mean", "mean_sea_level_pressure", np.asarray([previous_initialization]), previous_leads)
    state = xr.Dataset({variable: _load_cached_variable(cache, "ifs_hres_t0", variable, valid_times) for variable in ("mean_sea_level_pressure", "2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind")})
    precip = _load_cached_variable(cache, "ifs_hres_t0", "total_precipitation_6hr", precipitation_times).to_dataset(name="total_precipitation_6hr")
    stats.cache_hits = sum(1 for _ in cache_root.rglob("*.json"))
    return forecast, previous, state, precip, stats
