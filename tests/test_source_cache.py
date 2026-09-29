import json
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from forecast_bust.acquisition import AcquisitionStats, fetch_ens_variable
from forecast_bust.source_cache import CacheCorruptionError, SourceSliceCache, SourceSliceSpec, retry_transient


def _spec() -> SourceSliceSpec:
    return SourceSliceSpec(
        source_url="gs://example/source.zarr",
        source_version="v1",
        dataset="ifs_ens",
        variable="temperature",
        time_chunk=1,
        lead_chunk=2,
        levels_hpa=(),
        spatial_bounds=(6.0, 38.0, 68.0, 98.0),
    )


def _dataset() -> xr.Dataset:
    return xr.Dataset({"temperature": (("time", "latitude", "longitude"), np.arange(4.0).reshape(1, 2, 2), {"units": "K"})}, coords={"time": [np.datetime64("2020-06-01")], "latitude": [6.0, 7.5], "longitude": [68.0, 69.5]})


def test_cache_metadata_checksum_reuse_and_atomic_commit(tmp_path):
    cache = SourceSliceCache(tmp_path)
    spec = _spec()
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return _dataset()

    retry = lambda operation, _label: operation()
    first, hit1 = cache.get_or_fetch(spec, loader, retry)
    second, hit2 = cache.get_or_fetch(spec, loader, retry)
    assert not hit1 and hit2 and calls == 1
    assert first.equals(second)
    data_path, metadata_path = cache.paths(spec)
    metadata = json.loads(metadata_path.read_text())
    assert metadata["spec_sha256"] == spec.fingerprint
    assert metadata["units"] == {"temperature": "K"}
    assert metadata["source_times"] == ["2020-06-01T00:00:00.000000000"]
    assert metadata["spatial_bounds"] == [6.0, 38.0, 68.0, 98.0]
    assert not list(tmp_path.rglob("*.tmp-*"))
    assert data_path.exists()


def test_corrupted_cache_is_rejected_then_refetched(tmp_path):
    cache = SourceSliceCache(tmp_path)
    spec = _spec()
    cache.write(spec, _dataset())
    data_path, _ = cache.paths(spec)
    with data_path.open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(CacheCorruptionError, match="checksum"):
        cache.read(spec)
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return _dataset()

    result, hit = cache.get_or_fetch(spec, loader, lambda operation, _label: operation())
    assert not hit and calls == 1 and result.equals(_dataset())
    assert list(data_path.parent.glob("*.corrupt-*"))


def test_failed_write_has_no_commit_marker(tmp_path, monkeypatch):
    cache = SourceSliceCache(tmp_path)
    spec = _spec()

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(xr.Dataset, "to_netcdf", fail)
    with pytest.raises(OSError, match="disk full"):
        cache.write(spec, _dataset())
    data_path, metadata_path = cache.paths(spec)
    assert not data_path.exists() and not metadata_path.exists()


def test_retry_is_bounded_and_does_not_retry_validation(monkeypatch):
    monkeypatch.setattr("forecast_bust.source_cache.time.sleep", lambda _delay: None)
    attempts = 0

    def transient():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionResetError("reset")
        return _dataset()

    assert retry_transient(transient, "test", attempts=4).equals(_dataset())
    assert attempts == 3

    from forecast_bust.exceptions import ValidationError

    deterministic_attempts = 0

    def deterministic():
        nonlocal deterministic_attempts
        deterministic_attempts += 1
        raise ValidationError("bad units")

    with pytest.raises(ValidationError):
        retry_transient(deterministic, "test", attempts=4)
    assert deterministic_attempts == 1


def test_native_chunk_cache_avoids_duplicate_reads(ensemble_fixture, tmp_path):
    for variable in ensemble_fixture.data_vars:
        ensemble_fixture[variable].encoding["chunks"] = tuple(1 for _ in ensemble_fixture[variable].dims)
    cache = SourceSliceCache(tmp_path)
    stats = AcquisitionStats()
    first = fetch_ens_variable(
        ensemble_fixture,
        cache,
        "mean_sea_level_pressure",
        np.datetime64("2020-06-01T00"),
        (24,),
        stats=stats,
    )
    second = fetch_ens_variable(
        ensemble_fixture,
        cache,
        "mean_sea_level_pressure",
        np.datetime64("2020-06-01T00"),
        (24,),
        stats=stats,
    )
    assert first.equals(second)
    assert stats.cache_misses == 1
    assert stats.cache_hits == 1
