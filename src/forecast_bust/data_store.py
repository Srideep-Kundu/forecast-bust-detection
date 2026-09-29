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
        partitions = self.label_manifest.get("partitions", [])
        if not partitions or sum(int(item["rows"]) for item in partitions) != int(self.label_manifest.get("row_count", -1)):
            raise ValidationError("Labeled dataset manifest row count is inconsistent")
        for record in partitions:
            partition_path = self.resolve_recorded_path(record["path"])
            if not partition_path.exists() or sha256_file(partition_path) != record["sha256"]:
                raise ValidationError(f"Labeled partition hash mismatch: {partition_path.name}")
        for record in self.report["artifacts"].values():
            path = self.resolve_recorded_path(record["path"])
            if not path.exists() or sha256_file(path) != record["sha256"]:
                raise ValidationError(f"Model artifact hash mismatch: {path.name}")
            record["path"] = str(path)
        prediction = self.report["predictions"]
        prediction_path = self.resolve_recorded_path(prediction["path"])
        if not prediction_path.exists() or sha256_file(prediction_path) != prediction["sha256"]:
            raise ValidationError("Prediction artifact hash mismatch")
        prediction["path"] = str(prediction_path)
        self.prediction_path = prediction_path
        self._connection = duckdb.connect(":memory:")
        self._lock = threading.RLock()
        prediction_sql = prediction_path.resolve().as_posix().replace("'", "''")
        label_glob = (data_root / "labeled/year=*/month=*/labeled.parquet").resolve().as_posix().replace("'", "''")
        self._connection.execute(f"CREATE VIEW predictions AS SELECT * FROM read_parquet('{prediction_sql}')")
        self._connection.execute(f"CREATE VIEW labeled AS SELECT * FROM read_parquet('{label_glob}', union_by_name=true)")
        labeled_columns = {item[0] for item in self._connection.execute("DESCRIBE labeled").fetchall()}
        required_columns = set(self.report["feature_columns"]) | {
            "forecast_initialization_time", "valid_time", "region_name", "dataset_version",
            "bust", "severity", "e_precip_mm", "e_wind_mps", "e_temperature_k", "e_mslp_pa",
        }
        missing = sorted(required_columns - labeled_columns)
        if missing:
            raise ValidationError(f"Labeled dataset schema is missing fields: {missing}")

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
