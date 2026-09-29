import numpy as np
import polars as pl
import xarray as xr
import json

from forecast_bust.acquisition import fetch_cycle_source_slices, load_cycle_source_slices_from_cache
from forecast_bust.constants import LEAD_HOURS
from forecast_bust.corpus import derive_cycle_rows


def _sources():
    init = np.datetime64("2020-06-01T00", "ns")
    ens_times = np.asarray([init - np.timedelta64(12, "h"), init])
    leads = np.asarray(sorted(set(LEAD_HOURS) | {value + 12 for value in LEAD_HOURS}), dtype="timedelta64[h]")
    lat, lon, number, levels = [6.0, 7.5], [68.0, 69.5], np.arange(50), [500, 700, 850]
    surface_dims = ("time", "number", "prediction_timedelta", "longitude", "latitude")
    pressure_dims = surface_dims[:3] + ("level",) + surface_dims[3:]
    surface_shape = (2, 50, len(leads), 2, 2)
    pressure_shape = (2, 50, len(leads), 3, 2, 2)
    ramp = np.arange(np.prod(surface_shape), dtype=np.float32).reshape(surface_shape) / 10000
    ens = xr.Dataset(
        {
            "mean_sea_level_pressure": (surface_dims, 100000 + ramp, {"units": "Pa"}),
            "2m_temperature": (surface_dims, 295 + ramp, {"units": "K"}),
            "10m_u_component_of_wind": (surface_dims, 3 + ramp, {"units": "m s**-1"}),
            "10m_v_component_of_wind": (surface_dims, 4 + ramp, {"units": "m s**-1"}),
            "total_precipitation_24hr": (surface_dims, 0.01 + ramp / 1000),
            "u_component_of_wind": (pressure_dims, np.full(pressure_shape, 3.0, dtype=np.float32), {"units": "m s**-1"}),
            "v_component_of_wind": (pressure_dims, np.full(pressure_shape, 4.0, dtype=np.float32), {"units": "m s**-1"}),
            "geopotential": (pressure_dims, np.full(pressure_shape, 50000.0, dtype=np.float32), {"units": "m**2 s**-2"}),
        },
        coords={"time": ens_times, "number": number, "prediction_timedelta": leads, "level": levels, "longitude": lon, "latitude": lat},
    )
    for array in ens.data_vars.values():
        array.encoding["chunks"] = tuple({"time": 1, "number": 50, "prediction_timedelta": 4, "level": 3, "longitude": 2, "latitude": 2}[dim] for dim in array.dims)

    hres_times = np.arange(init + np.timedelta64(6, "h"), init + np.timedelta64(246, "h"), np.timedelta64(6, "h"))
    hshape = (len(hres_times), 2, 2)
    hdims = ("time", "longitude", "latitude")
    hres = xr.Dataset(
        {
            "mean_sea_level_pressure": (hdims, np.full(hshape, 100050.0), {"units": "Pa"}),
            "2m_temperature": (hdims, np.full(hshape, 296.0), {"units": "K"}),
            "10m_u_component_of_wind": (hdims, np.full(hshape, 2.5), {"units": "m s**-1"}),
            "10m_v_component_of_wind": (hdims, np.full(hshape, 3.5), {"units": "m s**-1"}),
            "total_precipitation_6hr": (hdims, np.full(hshape, 0.002), {"units": "m"}),
        },
        coords={"time": hres_times, "longitude": lon, "latitude": lat},
    )
    for array in hres.data_vars.values():
        array.encoding["chunks"] = (8, 2, 2)
    return init, ens, hres


def test_remote_then_cache_produces_identical_derived_rows(tmp_path):
    init, ens, hres = _sources()
    ens_mean = ens.mean("number", keep_attrs=True)
    for array in ens_mean.data_vars.values():
        array.encoding["chunks"] = tuple({"time": 1, "prediction_timedelta": 4, "level": 3, "longitude": 2, "latitude": 2}[dim] for dim in array.dims)
    weights = pl.DataFrame(
        [
            {"region_id": region, "region_name": f"Region {region}", "latitude": lat, "longitude": lon, "area_m2": 1.0, "weight": 0.25}
            for region in range(1, 37)
            for lat in (6.0, 7.5)
            for lon in (68.0, 69.5)
        ]
    )
    cache = tmp_path / "cache"
    first = fetch_cycle_source_slices(ens, ens_mean, hres, init, cache_root=cache, spread_features=("precip", "mslp", "wind"))
    first_rows, _ = derive_cycle_rows(*first[:4], weights, tmp_path / "weights", init)
    second = load_cycle_source_slices_from_cache(init, cache_root=cache, spread_features=("precip", "mslp", "wind"))
    second_rows, _ = derive_cycle_rows(*second[:4], weights, tmp_path / "weights", init)
    assert first_rows.equals(second_rows)
    assert first_rows.height == 360
    assert first[4].cache_misses > 0
    assert second[4].cache_misses == 0
    assert second[4].cache_hits > 0


def test_spread_configuration_uses_official_mean_and_skips_disabled_raw_reads(tmp_path):
    init, ens, hres = _sources()
    ens_mean = ens.mean("number", keep_attrs=True)
    for array in ens_mean.data_vars.values():
        array.encoding["chunks"] = tuple(
            {"time": 1, "prediction_timedelta": 4, "level": 3, "longitude": 2, "latitude": 2}[dim]
            for dim in array.dims
        )

    mean_cache = tmp_path / "mean-only"
    mean_result = fetch_cycle_source_slices(None, ens_mean, hres, init, cache_root=mean_cache)
    assert not [name for name in mean_result[0].data_vars if name.endswith("_spread")]
    assert not (mean_cache / "ifs_ens").exists()
    mean_metadata = [json.loads(path.read_text()) for path in mean_cache.rglob("*.json")]
    assert any(item["spec"]["dataset"] == "ifs_ens_mean" for item in mean_metadata)
    assert all(item["spec"]["source_url"] != "gs://weatherbench2/datasets/ifs_ens/2018-2022-240x121_equiangular_with_poles_conservative.zarr" for item in mean_metadata)

    precip_cache = tmp_path / "precip-only"
    first = fetch_cycle_source_slices(
        ens, ens_mean, hres, init, cache_root=precip_cache, spread_features=("precip",)
    )
    second = load_cycle_source_slices_from_cache(init, precip_cache, spread_features=("precip",))
    assert set(name for name in first[0].data_vars if name.endswith("_spread")) == {"total_precipitation_24hr_spread"}
    weights = pl.DataFrame(
        [
            {"region_id": region, "region_name": f"Region {region}", "latitude": lat, "longitude": lon, "area_m2": 1.0, "weight": 0.25}
            for region in range(1, 37)
            for lat in (6.0, 7.5)
            for lon in (68.0, 69.5)
        ]
    )
    first_rows, _ = derive_cycle_rows(*first[:4], weights, tmp_path / "weights", init)
    second_rows, _ = derive_cycle_rows(*second[:4], weights, tmp_path / "weights", init)
    assert first_rows.equals(second_rows)
    raw_metadata = [json.loads(path.read_text()) for path in (precip_cache / "ifs_ens").rglob("*.json")]
    assert {item["spec"]["variable"] for item in raw_metadata} == {"total_precipitation_24hr"}
    assert all(item["spec"]["dataset"] == "ifs_ens" for item in raw_metadata)
