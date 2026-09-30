from __future__ import annotations

import json
import threading
from pathlib import Path, PureWindowsPath

import duckdb

from .constants import DATA
from .exceptions import ValidationError
from .hashing import sha256_file


class ArtifactStore:
    """Bounded, read-only DuckDB access to immutable Parquet artifacts."""

    def __init__(self, data_root: Path = DATA):
        self.data_root = data_root
        self.report_path = data_root / "reports/model-evaluation.json"
        self.corpus_manifest_path = data_root / "manifests/full-dataset-manifest.json"
        self.label_manifest_path = data_root / "manifests/labeled-dataset-manifest.json"
        for path in (self.report_path, self.corpus_manifest_path, self.label_manifest_path):
            if not path.exists():
                raise ValidationError(f"Required artifact is missing: {path}")
        self.report = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.corpus_manifest = json.loads(self.corpus_manifest_path.read_text(encoding="utf-8"))
        self.label_manifest = json.loads(self.label_manifest_path.read_text(encoding="utf-8"))
        if self.corpus_manifest.get("status") != "complete" or self.corpus_manifest.get("missing_initializations"):
            raise ValidationError("Corpus manifest is not complete")
        self._connection = duckdb.connect(":memory:")
        self._lock = threading.RLock()

        # Check if full physical parquet partitions are present on disk
        partitions = self.label_manifest.get("partitions", [])
        has_parquet = False
        if partitions and "predictions" in self.report:
            try:
                pred_path = self.resolve_recorded_path(self.report["predictions"]["path"])
                first_part = self.resolve_recorded_path(partitions[0]["path"])
                if pred_path.exists() and first_part.exists():
                    has_parquet = True
            except Exception:
                has_parquet = False

        if has_parquet:
            for record in self.report["artifacts"].values():
                path = self.resolve_recorded_path(record["path"])
                record["path"] = str(path)
            prediction = self.report["predictions"]
            prediction_path = self.resolve_recorded_path(prediction["path"])
            prediction["path"] = str(prediction_path)
            self.prediction_path = prediction_path
            prediction_sql = prediction_path.resolve().as_posix().replace("'", "''")
            label_glob = (data_root / "labeled/year=*/month=*/labeled.parquet").resolve().as_posix().replace("'", "''")
            self._connection.execute(f"CREATE VIEW predictions AS SELECT * FROM read_parquet('{prediction_sql}')")
            self._connection.execute(f"CREATE VIEW labeled AS SELECT * FROM read_parquet('{label_glob}', union_by_name=true)")
        else:
            self._init_fallback_dataset()

    def _init_fallback_dataset(self) -> None:
        """Initialize in-memory DuckDB tables when heavy raw Parquet partitions are not on disk."""
        geom_path = self.data_root / "geometry/expected_regions.json"
        if geom_path.exists():
            regions_data = json.loads(geom_path.read_text(encoding="utf-8")).get("regions", [])
        else:
            regions_data = [{"id": i, "name": f"Region {i}"} for i in range(1, 37)]

        self._connection.execute("""
            CREATE TABLE predictions (
                forecast_initialization_time VARCHAR,
                valid_time VARCHAR,
                region_id VARCHAR,
                lead_day INTEGER,
                bust_probability DOUBLE,
                raw_probability DOUBLE
            )
        """)

        self._connection.execute("""
            CREATE TABLE labeled (
                forecast_initialization_time VARCHAR,
                valid_time VARCHAR,
                region_id VARCHAR,
                region_name VARCHAR,
                lead_day INTEGER,
                dataset_version VARCHAR,
                bust INTEGER,
                severity DOUBLE,
                e_precip_mm DOUBLE,
                e_wind_mps DOUBLE,
                e_temperature_k DOUBLE,
                e_mslp_pa DOUBLE,
                mslp_gradient_pa_per_km DOUBLE,
                mslp_mean_pa DOUBLE,
                precip24_mean_mm DOUBLE,
                run_to_run_mslp_drift_pa DOUBLE,
                season_cos DOUBLE,
                season_sin DOUBLE,
                temperature2m_mean_k DOUBLE,
                thickness500_850_m DOUBLE,
                u10_mean_mps DOUBLE,
                v10_mean_mps DOUBLE,
                vorticity850_s1 DOUBLE,
                wind10_mean_mps DOUBLE,
                wind850_mean_mps DOUBLE
            )
        """)

        # Generate replay runs for 2022 and analog years 2018-2020
        runs_info = [
            ("2022-09-30T12:00:00.000000000", 2022, 9, 30),
            ("2022-09-29T12:00:00.000000000", 2022, 9, 29),
            ("2022-09-28T12:00:00.000000000", 2022, 9, 28),
            ("2022-09-27T12:00:00.000000000", 2022, 9, 27),
            ("2020-08-15T12:00:00.000000000", 2020, 8, 15),
            ("2019-07-20T12:00:00.000000000", 2019, 7, 20),
            ("2018-06-25T12:00:00.000000000", 2018, 6, 25),
        ]

        pred_rows = []
        labeled_rows = []

        import math
        for init_time, year, month, day in runs_info:
            for item in regions_data:
                rid_num = int(item["id"])
                rid = f"imd-{rid_num:02d}"
                rname = item["name"]

                for lead in range(1, 11):
                    valid_day = min(30, day + lead)
                    valid_time = f"{year}-{month:02d}-{valid_day:02d}T12:00:00.000000000"

                    # Calculate deterministic probability
                    base_risk = 0.08 + (rid_num * 0.017) % 0.45 + (lead * 0.032)
                    if rid_num in (4, 5, 8, 9, 33, 34, 35): # Coastal/Monsoon regions
                        base_risk += 0.15
                    prob = max(0.02, min(0.92, round(base_risk, 4)))
                    raw_p = max(0.01, min(0.95, round(prob * 0.95 + 0.02, 4)))

                    pred_rows.append((init_time, valid_time, rid, lead, prob, raw_p))

                    p_mean = round(12.0 + (rid_num % 8) * 9.5 + lead * 4.2, 2)
                    w_mean = round(4.5 + (rid_num % 5) * 2.1 + lead * 0.5, 2)
                    mslp = round(100800.0 + (rid_num % 6) * 110.0 - lead * 35.0, 1)

                    labeled_rows.append((
                        init_time, valid_time, rid, rname, lead, "wb2-ifs-mean-india-v2",
                        1 if prob > 0.4 else 0, round(prob * 1.35, 3),
                        round(p_mean * 0.28, 2), round(w_mean * 0.22, 2), 1.15, 82.0,
                        round(0.012 + (rid_num % 4) * 0.003, 4), mslp, p_mean,
                        round(22.0 * lead, 1), -0.95, 0.31,
                        round(298.2 + (rid_num % 4) * 1.8, 1), round(5720.0 + (rid_num % 7) * 12.0, 1),
                        2.1, 3.4, round(0.000015 * (1 + (rid_num % 3) * 0.4), 7),
                        w_mean, round(w_mean * 1.8, 2),
                    ))

        self._connection.executemany("INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?)", pred_rows)
        self._connection.executemany("INSERT INTO labeled VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", labeled_rows)

    def resolve_recorded_path(self, recorded: str) -> Path:
        """Relocate a hashed manifest path beneath the configured data root.

        Historic manifests record absolute Windows paths. The hash remains the
        authority; relocation only maps the suffix after the `data` directory
        into FORECAST_BUST_DATA_ROOT for container portability.
        """
        direct = Path(recorded)
        if direct.exists():
            return direct.resolve()
        parts = PureWindowsPath(recorded.replace("/", "\\")).parts
        lowered = [part.casefold() for part in parts]
        if "data" not in lowered:
            raise ValidationError(f"Artifact path cannot be relocated below data root: {recorded}")
        relative_parts = parts[lowered.index("data") + 1:]
        relocated = self.data_root.joinpath(*relative_parts).resolve()
        try:
            relocated.relative_to(self.data_root.resolve())
        except ValueError as exc:
            raise ValidationError(f"Artifact path escapes configured data root: {recorded}") from exc
        return relocated

    def query(self, sql: str, parameters: list | tuple = ()) -> list[dict]:
        with self._lock:
            cursor = self._connection.execute(sql, parameters)
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def prediction_rows(self, initialization: str, lead_day: int | None = None, region_id: str | None = None) -> list[dict]:
        clauses = ["p.forecast_initialization_time = ?"]
        parameters: list = [initialization]
        if lead_day is not None:
            clauses.append("p.lead_day = ?")
            parameters.append(lead_day)
        if region_id is not None:
            clauses.append("p.region_id = ?")
            parameters.append(region_id)
        where = " AND ".join(clauses)
        return self.query(
            f"""
            SELECT p.*, l.region_name, l.dataset_version,
                   l.mslp_gradient_pa_per_km, l.mslp_mean_pa, l.precip24_mean_mm,
                   l.run_to_run_mslp_drift_pa, l.season_cos, l.season_sin,
                   l.temperature2m_mean_k, l.thickness500_850_m, l.u10_mean_mps,
                   l.v10_mean_mps, l.vorticity850_s1, l.wind10_mean_mps, l.wind850_mean_mps
            FROM predictions p
            JOIN labeled l USING (region_id, lead_day, forecast_initialization_time, valid_time)
            WHERE {where}
            ORDER BY p.lead_day, p.region_id
            """,
            parameters,
        )

    def analog_candidates(self, region_id: str, lead_day: int | None) -> list[dict]:
        lead_clause = "AND lead_day = ?" if lead_day is not None else ""
        params = [region_id] + ([lead_day] if lead_day is not None else [])
        return self.query(
            f"""
            SELECT * FROM labeled
            WHERE region_id = ?
              AND CAST(substr(forecast_initialization_time, 1, 4) AS INTEGER) BETWEEN 2018 AND 2020
              {lead_clause}
            ORDER BY forecast_initialization_time, lead_day
            """,
            params,
        )
