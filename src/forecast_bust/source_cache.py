from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import xarray as xr
import numpy as np

from .exceptions import ValidationError
from .hashing import sha256_file, sha256_json


class CacheCorruptionError(ValidationError):
    pass


@dataclass(frozen=True)
class SourceSliceSpec:
    source_url: str
    source_version: str
    dataset: str
    variable: str
    time_chunk: int
    lead_chunk: int | None
    levels_hpa: tuple[int, ...]
    spatial_bounds: tuple[float, float, float, float]

    @property
    def fingerprint(self) -> str:
        return sha256_json(asdict(self))


class SourceSliceCache:
    def __init__(self, root: Path):
        self.root = root

    def paths(self, spec: SourceSliceSpec) -> tuple[Path, Path]:
        directory = self.root / spec.dataset / spec.variable
        return directory / f"{spec.fingerprint}.nc", directory / f"{spec.fingerprint}.json"

    def read(self, spec: SourceSliceSpec) -> xr.Dataset | None:
        data_path, metadata_path = self.paths(spec)
        if not data_path.exists() and not metadata_path.exists():
            return None
        if not data_path.exists() or not metadata_path.exists():
            raise CacheCorruptionError(f"Incomplete cache artifact for {spec.variable}: {data_path}")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CacheCorruptionError(f"Unreadable cache metadata: {metadata_path}") from exc
        normalized_spec = json.loads(json.dumps(asdict(spec)))
        required_metadata = {"units", "shape", "source_times", "prediction_timedelta_hours", "pressure_levels_hpa", "spatial_bounds"}
        missing_metadata = sorted(required_metadata - set(metadata))
        if missing_metadata:
            raise CacheCorruptionError(f"Cache metadata lacks required provenance fields {missing_metadata}: {metadata_path}")
        if metadata.get("spec") != normalized_spec or metadata.get("spec_sha256") != spec.fingerprint:
            raise CacheCorruptionError(f"Cache metadata does not match requested source slice: {metadata_path}")
        if metadata.get("data_sha256") != sha256_file(data_path):
            raise CacheCorruptionError(f"Cache checksum mismatch: {data_path}")
        try:
            dataset = xr.load_dataset(data_path, engine="scipy")
        except Exception as exc:
            raise CacheCorruptionError(f"Unreadable cached NetCDF: {data_path}") from exc
        actual_shape = {name: int(size) for name, size in dataset.sizes.items()}
        if actual_shape != metadata.get("shape"):
            raise CacheCorruptionError(f"Cached shape mismatch for {data_path}: {actual_shape}")
        return dataset

    def _quarantine(self, spec: SourceSliceSpec) -> None:
        stamp = int(time.time())
        for path in self.paths(spec):
            if path.exists():
                os.replace(path, path.with_suffix(path.suffix + f".corrupt-{stamp}"))

    def write(self, spec: SourceSliceSpec, dataset: xr.Dataset) -> dict:
        data_path, metadata_path = self.paths(spec)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_data = data_path.with_suffix(f".nc.tmp-{os.getpid()}")
        temporary_metadata = metadata_path.with_suffix(f".json.tmp-{os.getpid()}")
        try:
            dataset.to_netcdf(temporary_data, engine="scipy")
            checksum = sha256_file(temporary_data)
            lead_values = []
            if "prediction_timedelta" in dataset.coords:
                values = np.asarray(dataset.prediction_timedelta.values)
                lead_values = (values / np.timedelta64(1, "h")).astype(int).tolist() if np.issubdtype(values.dtype, np.timedelta64) else values.astype(int).tolist()
            metadata = {
                "spec": json.loads(json.dumps(asdict(spec))),
                "spec_sha256": spec.fingerprint,
                "data_sha256": checksum,
                "variables": list(dataset.data_vars),
                "units": {name: dataset[name].attrs.get("units") for name in dataset.data_vars},
                "shape": {name: int(size) for name, size in dataset.sizes.items()},
                "source_times": [
                    np.datetime_as_string(np.datetime64(value, "ns"), unit="ns")
                    for value in np.atleast_1d(dataset.time.values)
                ] if "time" in dataset.coords else [],
                "prediction_timedelta_hours": lead_values,
                "pressure_levels_hpa": np.atleast_1d(dataset.level.values).astype(int).tolist() if "level" in dataset.coords else [],
                "spatial_bounds": list(spec.spatial_bounds),
                "bytes": temporary_data.stat().st_size,
            }
            temporary_metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temporary_data, data_path)
            # Metadata is the commit marker and is therefore renamed last.
            os.replace(temporary_metadata, metadata_path)
            return metadata
        finally:
            temporary_data.unlink(missing_ok=True)
            temporary_metadata.unlink(missing_ok=True)

    def get_or_fetch(
        self,
        spec: SourceSliceSpec,
        loader: Callable[[], xr.Dataset],
        retry: Callable[[Callable[[], xr.Dataset], str], xr.Dataset],
    ) -> tuple[xr.Dataset, bool]:
        try:
            cached = self.read(spec)
        except CacheCorruptionError:
            self._quarantine(spec)
            cached = None
        if cached is not None:
            return cached, True
        dataset = retry(loader, f"{spec.dataset}/{spec.variable}/time={spec.time_chunk}/lead={spec.lead_chunk}")
        if spec.variable not in dataset:
            raise ValidationError(f"Fetched slice lacks requested variable {spec.variable}")
        self.write(spec, dataset)
        verified = self.read(spec)
        if verified is None:
            raise CacheCorruptionError(f"Cache commit failed for {spec.variable}")
        return verified, False


def retry_transient(
    operation: Callable[[], xr.Dataset],
    label: str,
    attempts: int = 4,
    base_delay_seconds: float = 1.0,
) -> xr.Dataset:
    if attempts < 1:
        raise ValueError("attempts must be positive")
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except ValidationError:
            raise
        except (OSError, ConnectionError, TimeoutError) as exc:
            if attempt == attempts:
                raise
            delay = base_delay_seconds * (2 ** (attempt - 1))
            print(f"Transient read failure for {label}; retry {attempt}/{attempts - 1} in {delay:.1f}s: {exc}", flush=True)
            time.sleep(delay)
    raise AssertionError("unreachable")


def upgrade_cache_metadata(root: Path) -> dict:
    upgraded = 0
    for metadata_path in root.rglob("*.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        spec_value = metadata.get("spec")
        if not spec_value:
            continue
        spec_value["levels_hpa"] = tuple(spec_value["levels_hpa"])
        spec_value["spatial_bounds"] = tuple(spec_value["spatial_bounds"])
        spec = SourceSliceSpec(**spec_value)
        cache = SourceSliceCache(root)
        data_path, expected_metadata_path = cache.paths(spec)
        if expected_metadata_path != metadata_path or not data_path.exists():
            raise CacheCorruptionError(f"Cache artifact path does not match its spec: {metadata_path}")
        if metadata.get("data_sha256") != sha256_file(data_path):
            raise CacheCorruptionError(f"Cannot upgrade corrupt cache artifact: {data_path}")
        if {"source_times", "prediction_timedelta_hours", "pressure_levels_hpa", "spatial_bounds"}.issubset(metadata):
            continue
        dataset = xr.load_dataset(data_path, engine="scipy")
        cache.write(spec, dataset)
        upgraded += 1
    return {"cache_root": str(root), "upgraded_artifacts": upgraded}
