from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from forecast_bust.constants import ENS_URL, HRES_URL, LEAD_HOURS
from forecast_bust.weatherbench import lead_hours_values, normalize_coordinates, open_and_validate, select_india, select_leads, select_monsoon


def test_coordinate_normalization_and_geographic_slice() -> None:
    ds = xr.Dataset(coords={"lat": [9.0, 7.5, 6.0], "lon": [-292.0, -290.5, -289.0]})
    normalized = normalize_coordinates(ds)
    assert normalized.latitude.values.tolist() == [6.0, 7.5, 9.0]
    assert normalized.longitude.values.tolist() == [68.0, 69.5, 71.0]
    assert select_india(normalized).sizes == {"latitude": 3, "longitude": 3}


def test_exact_lead_filtering() -> None:
    ds = xr.Dataset(coords={"prediction_timedelta": np.asarray([0, *LEAD_HOURS, 246], dtype="timedelta64[h]")})
    selected = select_leads(ds)
    assert lead_hours_values(selected) == list(LEAD_HOURS)


def test_monsoon_filtering() -> None:
    ds = xr.Dataset(coords={"time": np.asarray(["2020-05-31", "2020-06-01", "2020-09-30", "2020-10-01"], dtype="datetime64[D]")})
    selected = select_monsoon(ds)
    assert selected.time.dt.month.values.tolist() == [6, 9]


@pytest.mark.cloud
def test_public_zarr_metadata_and_contract() -> None:
    ens, hres, report = open_and_validate()
    assert ens.sizes["number"] == 50
    assert {500, 850}.issubset(set(ens.level.values.tolist()))
    assert np.datetime64(ens.time.min().values) <= np.datetime64("2018-01-01")
    assert np.datetime64(ens.time.max().values) >= np.datetime64("2022-12-31")
    assert "total_precipitation_24hr" in ens
    assert "total_precipitation_6hr" in hres
    assert report["india_shape"]["latitude"] > 0
    assert report["india_shape"]["longitude"] > 0
    assert set(LEAD_HOURS).issubset(report["lead_hours"])
