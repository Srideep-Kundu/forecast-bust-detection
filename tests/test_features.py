from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest
import xarray as xr

from forecast_bust.constants import DATASET_VERSION, G0
from forecast_bust.exceptions import ValidationError
from forecast_bust.features import (
    ERROR_COLUMNS,
    FEATURE_COLUMNS,
    assert_feature_timestamp_isolation,
    build_forecast_feature_rows,
    build_verification_error_rows,
    geopotential_to_height,
    precipitation_to_mm,
    spherical_gradient_magnitude,
    spherical_relative_vorticity,
)
from forecast_bust.hashing import sha256_file
from forecast_bust.manifest import build_manifest
from forecast_bust.pipeline import compose_derived_rows


def _weights() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "region_id": [1] * 9,
            "region_name": ["Fixture"] * 9,
            "latitude": np.repeat([6.0, 7.5, 9.0], 3),
            "longitude": np.tile([68.0, 69.5, 71.0], 3),
            "area_m2": [1.0] * 9,
            "weight": [1 / 9] * 9,
        }
    )


def _selected_forecast(ensemble_fixture: xr.Dataset) -> xr.Dataset:
    return ensemble_fixture.sel(time=np.datetime64("2020-06-01T00"), prediction_timedelta=np.timedelta64(24, "h"))


def test_unit_conversions_and_spatial_derivatives(grid: xr.Dataset) -> None:
    geopotential = xr.DataArray(np.full((3, 3), G0 * 100), coords=grid.coords, dims=("latitude", "longitude"), attrs={"units": "m**2 s**-2"})
    height = geopotential_to_height(geopotential)
    assert height.attrs["units"] == "m"
    assert np.allclose(height, 100.0)
    precipitation = xr.DataArray([0.001, 0.002], attrs={"units": "m"})
    assert precipitation_to_mm(precipitation).values.tolist() == [1.0, 2.0]

    lat2d, lon2d = np.meshgrid(grid.latitude.values, grid.longitude.values, indexing="ij")
    pressure = xr.DataArray(100000 + lon2d * 100 + lat2d * 10, coords=grid.coords, dims=("latitude", "longitude"))
    gradient = spherical_gradient_magnitude(pressure)
    assert gradient.attrs["units"] == "Pa/km"
    assert np.isfinite(gradient).all()
    u = xr.zeros_like(pressure)
    v = xr.DataArray(lon2d, coords=grid.coords, dims=("latitude", "longitude"))
    vorticity = spherical_relative_vorticity(u, v)
    assert vorticity.attrs["units"] == "s^-1"
    assert np.isfinite(vorticity).all()


def test_feature_error_schema_timestamps_and_determinism(ensemble_fixture: xr.Dataset) -> None:
    forecast = _selected_forecast(ensemble_fixture)
    previous = forecast["mean_sea_level_pressure"]
    weights = _weights()
    first = build_forecast_feature_rows(forecast, previous, weights, np.datetime64("2020-06-01T00"), 24)
    second = build_forecast_feature_rows(forecast, previous, weights, np.datetime64("2020-06-01T00"), 24)
    assert first.equals(second)
    assert FEATURE_COLUMNS.issubset(first.columns)
    assert not any(name.startswith("analysis_") for name in first.columns)
    assert_feature_timestamp_isolation(first)

    analysis = xr.Dataset(
        {
            "mean_sea_level_pressure": forecast["mean_sea_level_pressure"].mean("number") - 100,
            "2m_temperature": forecast["2m_temperature"].mean("number") - 1,
            "10m_u_component_of_wind": forecast["10m_u_component_of_wind"].mean("number") - 1,
            "10m_v_component_of_wind": forecast["10m_v_component_of_wind"].mean("number"),
        }
    )
    analysis_precip = xr.full_like(forecast["total_precipitation_24hr"].mean("number"), 8.0)
    analysis_precip.attrs["units"] = "mm"
    errors = build_verification_error_rows(forecast, analysis, analysis_precip, weights)
    assert ERROR_COLUMNS.issubset(errors.columns)
    assert errors["e_precip_mm"][0] == pytest.approx(2.0)
    assert errors["e_wind_mps"][0] == pytest.approx(1.0)
    assert errors["e_temperature_k"][0] == pytest.approx(1.0)
    assert errors["e_mslp_pa"][0] == pytest.approx(100.0)
    derived_first = compose_derived_rows(first, errors)
    derived_second = compose_derived_rows(second, errors)
    assert derived_first.equals(derived_second)
    assert derived_first["region_id"].to_list() == ["imd-01"]
    assert derived_first["region_id_semantics"].to_list() == ["categorical"]


def test_timestamp_leakage_is_rejected() -> None:
    rows = pl.DataFrame({"feature_source_time": ["2020-06-02T00:00:00"], "forecast_initialization_time": ["2020-06-01T00:00:00"]})
    with pytest.raises(ValidationError):
        assert_feature_timestamp_isolation(rows)


def test_manifest_row_count_and_hash(tmp_path: Path) -> None:
    rows = pl.DataFrame(
        {
            "forecast_initialization_time": ["2020-06-01T00:00:00"],
            "valid_time": ["2020-06-02T00:00:00"],
            "dataset_version": [DATASET_VERSION],
        }
    )
    parquet = tmp_path / "sample.parquet"
    weights = tmp_path / "weights.parquet"
    rows.write_parquet(parquet)
    pl.DataFrame({"weight": [1.0]}).write_parquet(weights)
    manifest = build_manifest(parquet, rows, {}, {}, {}, [], weights)
    assert manifest["row_count"] == 1
    assert manifest["hashes"]["parquet_sha256"] == sha256_file(parquet)
    assert manifest["redistribution_enabled"] is False
