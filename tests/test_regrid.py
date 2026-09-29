from pathlib import Path

import pytest
import xarray as xr

from forecast_bust.exceptions import RegriddingUnavailableError
from forecast_bust.regrid import align_to_target


def test_identity_alignment_is_deterministic(grid: xr.Dataset, tmp_path: Path) -> None:
    source = grid.assign(foo=(("latitude", "longitude"), [[1,2,3],[4,5,6],[7,8,9]]))
    first, first_record = align_to_target(source, grid, ["foo"], "bilinear", tmp_path)
    second, second_record = align_to_target(source, grid, ["foo"], "bilinear", tmp_path)
    xr.testing.assert_identical(first, second)
    assert first_record["artifact_sha256"] == second_record["artifact_sha256"]


def test_nonmatching_grid_never_silently_aligns(grid: xr.Dataset, tmp_path: Path) -> None:
    source = xr.Dataset({"foo": (("latitude", "longitude"), [[1,2],[3,4]])}, coords={"latitude":[6.0,9.0],"longitude":[68.0,71.0]})
    try:
        aligned, record = align_to_target(source, grid, ["foo"], "bilinear", tmp_path)
        assert aligned.sizes == grid.sizes
        assert record["alignment"] == "xesmf"
    except RegriddingUnavailableError as exc:
        assert "ESMF" in str(exc)
