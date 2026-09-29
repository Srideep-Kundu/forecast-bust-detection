from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import xarray as xr

from .constants import ENS_MEAN_URL, ENS_REQUIRED, ENS_URL, HRES_REQUIRED, HRES_URL, INDIA_BOUNDS, LEAD_HOURS, MONSOON_MONTHS
from .exceptions import ValidationError


def open_public_zarr(url: str, filesystem=None) -> xr.Dataset:
    if filesystem is None:
        return xr.open_zarr(url, consolidated=True, storage_options={"token": "anon"})
    path = url.removeprefix("gs://")
    return xr.open_zarr(filesystem.get_mapper(path), consolidated=True)


def lead_hours_values(ds: xr.Dataset) -> list[int]:
    values = np.asarray(ds.prediction_timedelta.values)
    if np.issubdtype(values.dtype, np.timedelta64):
        return (values / np.timedelta64(1, "h")).astype(int).tolist()
    units = ds.prediction_timedelta.attrs.get("units")
    if units != "hours":
        raise ValidationError(f"Numeric prediction_timedelta has units={units!r}; expected 'hours'")
    return values.astype(int).tolist()


def lead_selector(ds: xr.Dataset, hours: int | list[int] | tuple[int, ...]):
    values = np.asarray(ds.prediction_timedelta.values)
    requested = np.asarray(hours)
    if np.issubdtype(values.dtype, np.timedelta64):
        selected = requested.astype("timedelta64[h]")
    else:
        if ds.prediction_timedelta.attrs.get("units") != "hours":
            raise ValidationError("Cannot select numeric forecast leads without units='hours'")
        selected = requested.astype(int)
    return selected.item() if selected.ndim == 0 else selected


def normalize_coordinates(ds: xr.Dataset) -> xr.Dataset:
    renames = {}
    if "lat" in ds.coords and "latitude" not in ds.coords:
        renames["lat"] = "latitude"
    if "lon" in ds.coords and "longitude" not in ds.coords:
        renames["lon"] = "longitude"
    ds = ds.rename(renames)
    for coord in ("latitude", "longitude"):
        if coord not in ds.coords:
            raise ValidationError(f"Missing required coordinate: {coord}")
    longitude = np.mod(ds.longitude.astype("float64"), 360.0)
    ds = ds.assign_coords(longitude=longitude).sortby("longitude").sortby("latitude")
    for coord in ("latitude", "longitude"):
        values = np.asarray(ds[coord].values)
        if not np.all(np.isfinite(values)) or len(np.unique(values)) != len(values):
            raise ValidationError(f"Coordinate {coord} is non-finite or contains duplicates")
        if np.any(np.diff(values) <= 0):
            raise ValidationError(f"Coordinate {coord} is not strictly increasing")
    return ds


def _validate_units(ds: xr.Dataset, required: Mapping[str, tuple[str, ...]], label: str) -> None:
    missing = sorted(set(required) - set(ds.data_vars))
    if missing:
        available = sorted(ds.data_vars)
        raise ValidationError(f"{label} missing variables {missing}; available={available}")
    for name, allowed in required.items():
        if not allowed:
            continue
        actual = ds[name].attrs.get("units")
        if actual not in allowed:
            raise ValidationError(f"{label}.{name} units={actual!r}; expected one of {allowed}")


def validate_remote_datasets(ens: xr.Dataset, hres: xr.Dataset) -> dict:
    _validate_units(ens, ENS_REQUIRED, "IFS_ENS")
    _validate_units(hres, HRES_REQUIRED, "IFS_HRES")
    expected_dims = {"time", "number", "prediction_timedelta", "longitude", "latitude", "level"}
    if not expected_dims.issubset(ens.dims):
        raise ValidationError(f"IFS_ENS dimensions={sorted(ens.dims)}; missing={sorted(expected_dims-set(ens.dims))}")
    if ens.sizes["number"] != 50:
        raise ValidationError(f"IFS_ENS member count={ens.sizes['number']}; expected 50")
    leads = set(lead_hours_values(ens))
    missing_leads = sorted(set(LEAD_HOURS) - leads)
    if missing_leads:
        raise ValidationError(f"IFS_ENS missing lead hours {missing_leads}")
    levels = set(np.asarray(ens.level.values).astype(int).tolist())
    if not {500, 850}.issubset(levels):
        raise ValidationError(f"IFS_ENS pressure levels={sorted(levels)}; require 500 and 850 hPa")
    start, stop = np.datetime64(ens.time.min().values), np.datetime64(ens.time.max().values)
    if start > np.datetime64("2018-01-01") or stop < np.datetime64("2022-12-31"):
        raise ValidationError(f"IFS_ENS coverage {start}..{stop} does not cover 2018-2022")
    if int(ens.time.dt.month.isin(MONSOON_MONTHS).sum()) == 0:
        raise ValidationError("IFS_ENS June-September selection is empty")
    subset = select_india(ens)
    if subset.sizes["latitude"] == 0 or subset.sizes["longitude"] == 0:
        raise ValidationError("IFS_ENS India domain selection is empty")
    # WB2 derived precipitation lacks copied attrs. Confirm its source field is metres.
    if ens["total_precipitation_24hr"].attrs.get("units") not in (None, "m"):
        raise ValidationError("Unexpected units on total_precipitation_24hr")
    return {
        "ens_dimensions": dict(ens.sizes),
        "hres_dimensions": dict(hres.sizes),
        "ens_variables": sorted(ens.data_vars),
        "hres_variables": sorted(hres.data_vars),
        "ens_coverage": [str(start), str(stop)],
        "lead_hours": sorted(leads),
        "pressure_levels_hpa": sorted(levels),
        "india_shape": {"latitude": subset.sizes["latitude"], "longitude": subset.sizes["longitude"]},
        "precipitation_24hr_units": "m (inherited from total_precipitation per WeatherBench derived-variable definition)",
    }


def select_india(ds: xr.Dataset) -> xr.Dataset:
    return ds.sel(
        latitude=slice(INDIA_BOUNDS["latitude_min"], INDIA_BOUNDS["latitude_max"]),
        longitude=slice(INDIA_BOUNDS["longitude_min"], INDIA_BOUNDS["longitude_max"]),
    )


def select_monsoon(ds: xr.Dataset) -> xr.Dataset:
    return ds.sel(time=ds.time.dt.month.isin(MONSOON_MONTHS))


def select_leads(ds: xr.Dataset) -> xr.Dataset:
    requested = lead_selector(ds, LEAD_HOURS)
    selected = ds.sel(prediction_timedelta=requested)
    actual = lead_hours_values(selected)
    if tuple(actual) != LEAD_HOURS:
        raise ValidationError(f"Lead selection returned {actual}; expected {LEAD_HOURS}")
    return selected


def open_and_validate(filesystem=None) -> tuple[xr.Dataset, xr.Dataset, dict]:
    ens = normalize_coordinates(open_public_zarr(ENS_URL, filesystem=filesystem))
    hres = normalize_coordinates(open_public_zarr(HRES_URL, filesystem=filesystem))
    report = validate_remote_datasets(ens, hres)
    return ens, hres, report


def open_sources_and_validate(filesystem=None) -> tuple[xr.Dataset, xr.Dataset, xr.Dataset, dict]:
    ens, hres, report = open_and_validate(filesystem=filesystem)
    ens_mean = normalize_coordinates(open_public_zarr(ENS_MEAN_URL, filesystem=filesystem))
    _validate_units(ens_mean, ENS_REQUIRED, "IFS_ENS_MEAN")
    if "number" in ens_mean.dims:
        raise ValidationError("Official IFS ENS mean unexpectedly contains a member dimension")
    required_dims = {"time", "prediction_timedelta", "longitude", "latitude", "level"}
    if not required_dims.issubset(ens_mean.dims):
        raise ValidationError(f"IFS_ENS_MEAN dimensions={sorted(ens_mean.dims)}; missing={sorted(required_dims-set(ens_mean.dims))}")
    for coordinate in ("time", "prediction_timedelta", "longitude", "latitude", "level"):
        if not np.array_equal(ens[coordinate].values, ens_mean[coordinate].values):
            raise ValidationError(f"IFS ENS mean {coordinate} does not align with the full ensemble")
    report["ens_mean_url"] = ENS_MEAN_URL
    report["ens_mean_dimensions"] = dict(ens_mean.sizes)
    report["ens_mean_variables"] = sorted(ens_mean.data_vars)
    return ens, ens_mean, hres, report


def open_mean_sources_and_validate(filesystem=None) -> tuple[xr.Dataset, xr.Dataset, dict]:
    """Open production MVP sources without touching full-member ENS arrays."""
    ens_mean = normalize_coordinates(open_public_zarr(ENS_MEAN_URL, filesystem=filesystem))
    hres = normalize_coordinates(open_public_zarr(HRES_URL, filesystem=filesystem))
    _validate_units(ens_mean, ENS_REQUIRED, "IFS_ENS_MEAN")
    _validate_units(hres, HRES_REQUIRED, "IFS_HRES")
    if "number" in ens_mean.dims:
        raise ValidationError("Official IFS ENS mean unexpectedly contains a member dimension")
    required_dims = {"time", "prediction_timedelta", "longitude", "latitude", "level"}
    if not required_dims.issubset(ens_mean.dims):
        raise ValidationError(f"IFS_ENS_MEAN dimensions={sorted(ens_mean.dims)}; missing={sorted(required_dims-set(ens_mean.dims))}")
    leads = set(lead_hours_values(ens_mean))
    missing_leads = sorted(set(LEAD_HOURS) - leads)
    if missing_leads:
        raise ValidationError(f"IFS_ENS_MEAN missing lead hours {missing_leads}")
    levels = set(np.asarray(ens_mean.level.values).astype(int).tolist())
    if not {500, 850}.issubset(levels):
        raise ValidationError(f"IFS_ENS_MEAN pressure levels={sorted(levels)}; require 500 and 850 hPa")
    start, stop = np.datetime64(ens_mean.time.min().values), np.datetime64(ens_mean.time.max().values)
    if start > np.datetime64("2018-01-01") or stop < np.datetime64("2022-12-31"):
        raise ValidationError(f"IFS_ENS_MEAN coverage {start}..{stop} does not cover 2018-2022")
    subset = select_india(ens_mean)
    if subset.sizes["latitude"] == 0 or subset.sizes["longitude"] == 0:
        raise ValidationError("IFS_ENS_MEAN India domain selection is empty")
    return ens_mean, hres, {
        "feature_contract": "mean-only-mvp-v2",
        "ens_mean_url": ENS_MEAN_URL,
        "raw_ensemble_member_access": False,
        "ens_mean_dimensions": dict(ens_mean.sizes),
        "hres_dimensions": dict(hres.sizes),
        "ens_mean_variables": sorted(ens_mean.data_vars),
        "hres_variables": sorted(hres.data_vars),
        "lead_hours": sorted(leads),
        "pressure_levels_hpa": sorted(levels),
        "india_shape": {"latitude": subset.sizes["latitude"], "longitude": subset.sizes["longitude"]},
    }
