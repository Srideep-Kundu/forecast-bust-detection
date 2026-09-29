from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from .constants import GRID_TOLERANCE_DEG
from .exceptions import RegriddingUnavailableError, ValidationError
from .hashing import sha256_file, sha256_json, write_json


def grid_signature(ds: xr.Dataset) -> dict:
    return {
        "latitude": np.asarray(ds.latitude.values, dtype=float).round(10).tolist(),
        "longitude": np.asarray(ds.longitude.values, dtype=float).round(10).tolist(),
    }


def grids_match(source: xr.Dataset, target: xr.Dataset) -> bool:
    return (
        source.sizes.get("latitude") == target.sizes.get("latitude")
        and source.sizes.get("longitude") == target.sizes.get("longitude")
        and np.allclose(source.latitude.values, target.latitude.values, atol=GRID_TOLERANCE_DEG, rtol=0)
        and np.allclose(source.longitude.values, target.longitude.values, atol=GRID_TOLERANCE_DEG, rtol=0)
    )


def align_to_target(
    source: xr.Dataset,
    target: xr.Dataset,
    variables: list[str],
    method: str,
    artifact_dir: Path,
) -> tuple[xr.Dataset, dict]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    source_sig, target_sig = grid_signature(source), grid_signature(target)
    if grids_match(source, target):
        aligned = source[variables].reindex(latitude=target.latitude, longitude=target.longitude)
        if not grids_match(aligned, target):
            raise ValidationError("Exact alignment did not reproduce target coordinates")
        record = {
            "alignment": "identity",
            "requested_method": method,
            "source_grid_sha256": sha256_json(source_sig),
            "target_grid_sha256": sha256_json(target_sig),
            "tolerance_degrees": GRID_TOLERANCE_DEG,
            "weight_file": None,
        }
        path = artifact_dir / f"identity-{method}.json"
        write_json(path, record)
        record["artifact_path"] = str(path)
        record["artifact_sha256"] = sha256_file(path)
        return aligned, record

    if method not in {"conservative", "bilinear"}:
        raise ValidationError(f"Unsupported regridding method {method}")
    try:
        import xesmf as xe
    except (ImportError, ModuleNotFoundError) as exc:
        raise RegriddingUnavailableError(
            "Non-identical grids require xESMF with the native ESMF/esmpy backend; install ESMF before retrying"
        ) from exc
    weights = artifact_dir / f"hres-to-ens-{method}.nc"
    regridder = xe.Regridder(source, target, method, filename=str(weights), reuse_weights=weights.exists())
    aligned = regridder(source[variables], keep_attrs=True)
    if not grids_match(aligned, target):
        raise ValidationError("Regridded output does not match target coordinates")
    record = {
        "alignment": "xesmf",
        "method": method,
        "xesmf_version": xe.__version__,
        "source_grid_sha256": sha256_json(source_sig),
        "target_grid_sha256": sha256_json(target_sig),
        "weight_file": str(weights),
        "weight_sha256": sha256_file(weights),
    }
    path = artifact_dir / f"hres-to-ens-{method}.json"
    write_json(path, record)
    record["artifact_path"] = str(path)
    record["artifact_sha256"] = sha256_file(path)
    return aligned, record
