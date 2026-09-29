import numpy as np
import polars as pl

from forecast_bust.labels import apply_label_artifacts, fit_label_artifacts


def _rows(test_offset: float = 0.0) -> pl.DataFrame:
    records = []
    for year in range(2018, 2023):
        count = 40 if year <= 2020 else 20
        for region in ("imd-01", "imd-02"):
            for lead in (1, 2):
                for index in range(count):
                    value = float(index + (test_offset if year == 2022 else 0.0))
                    records.append(
                        {
                            "forecast_initialization_time": f"{year}-06-{index % 28 + 1:02d}T00:00:00.000000000",
                            "region_id": region,
                            "lead_day": lead,
                            "e_precip_mm": value,
                            "e_mslp_pa": value * 2,
                            "e_wind_mps": value / 3,
                            "e_temperature_k": value / 4,
                        }
                    )
    return pl.DataFrame(records)


def test_label_fit_is_unchanged_when_2022_is_mutated():
    artifact_a, _ = fit_label_artifacts(_rows(0.0))
    artifact_b, _ = fit_label_artifacts(_rows(1_000_000.0))
    assert artifact_a == artifact_b


def test_labels_use_strict_threshold_and_clipping():
    rows = _rows(1_000_000.0)
    artifact, _ = fit_label_artifacts(rows)
    labeled = apply_label_artifacts(rows, artifact)
    assert labeled["bust"].dtype == pl.Int8
    assert labeled["z_precip"].min() >= -8
    assert labeled["z_precip"].max() <= 8
    expected = (labeled["severity"] > labeled["threshold"]).cast(pl.Int8)
    assert np.array_equal(expected.to_numpy(), labeled["bust"].to_numpy())
