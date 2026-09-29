from __future__ import annotations

import math

import numpy as np
import polars as pl
import xarray as xr

from .constants import EARTH_RADIUS_M, G0
from .exceptions import ValidationError


FEATURE_COLUMNS = {
    "mslp_mean_pa",
    "mslp_gradient_pa_per_km",
    "temperature2m_mean_k",
    "u10_mean_mps",
    "v10_mean_mps",
    "wind10_mean_mps",
    "wind850_mean_mps",
    "vorticity850_s1",
    "thickness500_850_m",
    "precip24_mean_mm",
    "run_to_run_mslp_drift_pa",
    "season_sin",
    "season_cos",
}

ERROR_COLUMNS = {"e_precip_mm", "e_wind_mps", "e_temperature_k", "e_mslp_pa"}


def geopotential_to_height(geopotential: xr.DataArray) -> xr.DataArray:
    if geopotential.attrs.get("units") != "m**2 s**-2":
        raise ValidationError(f"Geopotential units={geopotential.attrs.get('units')!r}; expected m**2 s**-2")
    result = geopotential / G0
    result.attrs["units"] = "m"
    return result


def precipitation_to_mm(precipitation: xr.DataArray, inherited_units: str | None = None) -> xr.DataArray:
    units = precipitation.attrs.get("units") or inherited_units
    if units == "m":
        result = precipitation * 1000.0
    elif units == "mm":
        result = precipitation.copy()
    else:
        raise ValidationError(f"Precipitation units={units!r}; expected m or mm")
    result.attrs["units"] = "mm"
    return result


def spherical_gradient_magnitude(field: xr.DataArray) -> xr.DataArray:
    grid = field.transpose("latitude", "longitude")
    lat = np.deg2rad(grid.latitude.values.astype(float))
    lon = np.deg2rad(grid.longitude.values.astype(float))
    values = np.asarray(grid.values, dtype=float)
    d_dlat = np.gradient(values, lat, axis=0, edge_order=1) / EARTH_RADIUS_M
    d_dlon = np.gradient(values, lon, axis=1, edge_order=1) / (EARTH_RADIUS_M * np.cos(lat)[:, None])
    result = xr.DataArray(np.sqrt(d_dlat**2 + d_dlon**2) * 1000.0, coords=grid.coords, dims=grid.dims)
    result.attrs["units"] = "Pa/km"
    return result


def spherical_relative_vorticity(u: xr.DataArray, v: xr.DataArray) -> xr.DataArray:
    u_grid, v_grid = u.transpose("latitude", "longitude"), v.transpose("latitude", "longitude")
    lat = np.deg2rad(u_grid.latitude.values.astype(float))
    lon = np.deg2rad(u_grid.longitude.values.astype(float))
    du_dlat = np.gradient(np.asarray(u_grid.values, dtype=float), lat, axis=0, edge_order=1) / EARTH_RADIUS_M
    dv_dlon = np.gradient(np.asarray(v_grid.values, dtype=float), lon, axis=1, edge_order=1) / (EARTH_RADIUS_M * np.cos(lat)[:, None])
    result = xr.DataArray(dv_dlon - du_dlat, coords=u_grid.coords, dims=u_grid.dims)
    result.attrs["units"] = "s^-1"
    return result


def _weighted_regions(array: xr.DataArray, weights: pl.DataFrame, output_name: str) -> pl.DataFrame:
    grid = array.transpose("latitude", "longitude").to_dataframe(name="value").reset_index()
    frame = pl.from_pandas(grid[["latitude", "longitude", "value"]])
    joined = weights.join(frame, on=["latitude", "longitude"], how="left")
    if joined["value"].null_count() or not joined["value"].is_finite().all():
        raise ValidationError(f"Missing/non-finite values while aggregating {output_name}")
    return joined.group_by(["region_id", "region_name"]).agg((pl.col("value") * pl.col("weight")).sum().alias(output_name))


def build_forecast_feature_rows(
    forecast: xr.Dataset,
    previous_mslp: xr.DataArray,
    weights: pl.DataFrame,
    initialization: np.datetime64,
    lead_hours: int,
) -> pl.DataFrame:
    def mean_field(name: str) -> xr.DataArray:
        field = forecast[name]
        return field.mean("number") if "number" in field.dims else field

    def spread_field(name: str) -> xr.DataArray:
        spread_name = f"{name}_spread"
        if spread_name in forecast:
            return forecast[spread_name]
        if "number" not in forecast[name].dims:
            raise ValidationError(f"Forecast mean field {name} has no corresponding ensemble spread")
        return forecast[name].std("number")

    mslp = mean_field("mean_sea_level_pressure")
    gradient = spherical_gradient_magnitude(mslp)
    u850 = mean_field("u_component_of_wind").sel(level=850)
    v850 = mean_field("v_component_of_wind").sel(level=850)
    wind850 = np.hypot(u850, v850)
    vorticity = spherical_relative_vorticity(u850, v850)
    heights = geopotential_to_height(mean_field("geopotential"))
    thickness = heights.sel(level=500) - heights.sel(level=850)
    thickness.attrs["units"] = "m"
    precip_mean = precipitation_to_mm(mean_field("total_precipitation_24hr"), inherited_units="m")
    previous_mean = previous_mslp.mean("number") if "number" in previous_mslp.dims else previous_mslp
    drift = abs(mslp - previous_mean)
    arrays = {
        "mslp_mean_pa": mslp,
        "mslp_gradient_pa_per_km": gradient,
        "temperature2m_mean_k": mean_field("2m_temperature"),
        "u10_mean_mps": mean_field("10m_u_component_of_wind"),
        "v10_mean_mps": mean_field("10m_v_component_of_wind"),
        "wind10_mean_mps": np.hypot(mean_field("10m_u_component_of_wind"), mean_field("10m_v_component_of_wind")),
        "wind850_mean_mps": wind850,
        "vorticity850_s1": vorticity,
        "thickness500_850_m": thickness,
        "precip24_mean_mm": precip_mean,
        "run_to_run_mslp_drift_pa": drift,
    }
    optional_spreads = {
        "mean_sea_level_pressure": ("mslp_spread_pa", lambda value: value),
        "2m_temperature": ("temperature2m_spread_k", lambda value: value),
        "10m_u_component_of_wind": ("u10_spread_mps", lambda value: value),
        "10m_v_component_of_wind": ("v10_spread_mps", lambda value: value),
        "total_precipitation_24hr": (
            "precip24_spread_mm",
            lambda value: precipitation_to_mm(value, inherited_units="m"),
        ),
    }
    for source_name, (output_name, convert) in optional_spreads.items():
        explicit_name = f"{source_name}_spread"
        if explicit_name in forecast or ("number" in forecast[source_name].dims and source_name != "2m_temperature"):
            arrays[output_name] = convert(spread_field(source_name))
    base = weights.select(["region_id", "region_name"]).unique().sort("region_id")
    for name, array in arrays.items():
        base = base.join(_weighted_regions(array, weights, name), on=["region_id", "region_name"])
    timestamp = np.datetime64(initialization, "ns")
    day = int(str(timestamp).split("T")[0].split("-")[-1])
    month = int(str(timestamp).split("T")[0].split("-")[1])
    doy = int(np.datetime64(timestamp, "D").astype(object).timetuple().tm_yday)
    valid = timestamp + np.timedelta64(lead_hours, "h")
    return base.with_columns(
        pl.lit(str(timestamp)).alias("forecast_initialization_time"),
        pl.lit(str(timestamp)).alias("feature_source_time"),
        pl.lit(str(valid)).alias("valid_time"),
        pl.lit(lead_hours // 24).alias("lead_day"),
        pl.lit(math.sin(2 * math.pi * doy / 366)).alias("season_sin"),
        pl.lit(math.cos(2 * math.pi * doy / 366)).alias("season_cos"),
    )


def build_verification_error_rows(
    forecast: xr.Dataset,
    analysis: xr.Dataset,
    analysis_precip24_mm: xr.DataArray,
    weights: pl.DataFrame,
) -> pl.DataFrame:
    def mean_field(name: str) -> xr.DataArray:
        field = forecast[name]
        return field.mean("number") if "number" in field.dims else field

    f_precip = precipitation_to_mm(mean_field("total_precipitation_24hr"), inherited_units="m")
    f_u = mean_field("10m_u_component_of_wind")
    f_v = mean_field("10m_v_component_of_wind")
    e_wind = np.hypot(f_u - analysis["10m_u_component_of_wind"], f_v - analysis["10m_v_component_of_wind"])
    e_temp = abs(mean_field("2m_temperature") - analysis["2m_temperature"])
    e_mslp = abs(mean_field("mean_sea_level_pressure") - analysis["mean_sea_level_pressure"])
    f_precip_region = _weighted_regions(f_precip, weights, "forecast_precip_mm")
    a_precip_region = _weighted_regions(analysis_precip24_mm, weights, "analysis_precip_mm")
    result = f_precip_region.join(a_precip_region, on=["region_id", "region_name"]).with_columns(
        (pl.col("forecast_precip_mm") - pl.col("analysis_precip_mm")).abs().alias("e_precip_mm")
    ).drop(["forecast_precip_mm", "analysis_precip_mm"])
    for name, array in (("e_wind_mps", e_wind), ("e_temperature_k", e_temp), ("e_mslp_pa", e_mslp)):
        result = result.join(_weighted_regions(array, weights, name), on=["region_id", "region_name"])
    return result.sort("region_id")


def assert_feature_timestamp_isolation(rows: pl.DataFrame) -> None:
    bad = rows.filter(pl.col("feature_source_time").str.to_datetime() > pl.col("forecast_initialization_time").str.to_datetime())
    if bad.height:
        raise ValidationError("feature_source_time exceeds forecast_initialization_time")
    forbidden = [name for name in rows.columns if name.startswith("analysis_") or name.startswith("verification_")]
    if forbidden:
        raise ValidationError(f"Verification fields leaked into feature rows: {forbidden}")
