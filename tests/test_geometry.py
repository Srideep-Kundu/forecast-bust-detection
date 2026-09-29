from pathlib import Path

import numpy as np
import polars as pl
import pytest

from forecast_bust.geometry import acquire_geometry, compute_region_weights, load_expected_manifest, validate_and_canonicalize_geometry


@pytest.mark.integration
def test_real_geometry_validation_and_area_weights(tmp_path: Path) -> None:
    source, hashes = acquire_geometry(tmp_path / "cache")
    regions, report = validate_and_canonicalize_geometry(
        source,
        tmp_path / "canonical.geojson",
        tmp_path / "validation.json",
        load_expected_manifest(),
        allow_make_valid=True,
    )
    assert len(hashes) == 5
    assert len(regions) == 36
    assert {item["id"] for item in report["invalid_source_geometries"]} == {34, 36}
    assert max(item["area_km2"] for item in report["topology_overlaps"]) <= report["overlap_tolerance_km2"]
    weights = compute_region_weights(regions, np.arange(6.0, 39.0, 1.5), np.arange(67.5, 99.0, 1.5))
    sums = weights.group_by("region_id").agg(pl.col("weight").sum().alias("weight_sum"))
    assert weights["region_id"].n_unique() == 36
    assert all(abs(value - 1.0) <= 1e-8 for value in sums["weight_sum"])
