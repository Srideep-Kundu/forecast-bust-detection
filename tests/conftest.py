from __future__ import annotations

import numpy as np
import pytest
import xarray as xr


@pytest.fixture
def grid() -> xr.Dataset:
    return xr.Dataset(coords={"latitude": [6.0, 7.5, 9.0], "longitude": [68.0, 69.5, 71.0]})


@pytest.fixture
def ensemble_fixture(grid: xr.Dataset) -> xr.Dataset:
    shape = (2, 50, 3, 3, 3)
    coords = {
        "time": np.asarray(["2020-06-01T00", "2020-06-01T12"], dtype="datetime64[h]"),
        "number": np.arange(50),
        "prediction_timedelta": np.asarray([24, 48, 240], dtype="timedelta64[h]"),
        "longitude": grid.longitude,
        "latitude": grid.latitude,
        "level": [500, 700, 850],
    }
    surface_dims = ("time", "number", "prediction_timedelta", "longitude", "latitude")
    pressure_dims = ("time", "number", "prediction_timedelta", "level", "longitude", "latitude")
    pressure_shape = (2, 50, 3, 3, 3, 3)
    data = {
        "mean_sea_level_pressure": (surface_dims, np.full(shape, 100000.0), {"units": "Pa"}),
        "2m_temperature": (surface_dims, np.full(shape, 300.0), {"units": "K"}),
        "10m_u_component_of_wind": (surface_dims, np.full(shape, 3.0), {"units": "m s**-1"}),
        "10m_v_component_of_wind": (surface_dims, np.full(shape, 4.0), {"units": "m s**-1"}),
        "total_precipitation": (surface_dims, np.full(shape, 0.01), {"units": "m"}),
        "total_precipitation_24hr": (surface_dims, np.full(shape, 0.01)),
        "u_component_of_wind": (pressure_dims, np.full(pressure_shape, 3.0), {"units": "m s**-1"}),
        "v_component_of_wind": (pressure_dims, np.full(pressure_shape, 4.0), {"units": "m s**-1"}),
        "geopotential": (pressure_dims, np.full(pressure_shape, 50000.0), {"units": "m**2 s**-2"}),
    }
    return xr.Dataset(data, coords=coords)
