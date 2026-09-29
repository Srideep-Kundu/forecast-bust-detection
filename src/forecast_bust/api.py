from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .constants import DATA, DATASET_VERSION, FEATURE_CONTRACT_VERSION
from .contracts import (
    CopilotRequest, CopilotResponse, ForecastRun, HealthResponse, LeadCurveResponse,
    LeadRiskPoint, ModelMetadata, PredictionExplanation, Region, RegionRisk, RiskMapResponse,
)
from .copilot import LLMExplanationService
from .data_store import ArtifactStore
from .evidence import EvidenceEngine
from .exceptions import ValidationError
from .hashing import sha256_file
from .identity import parse_prediction_id, parse_run_id, prediction_id as make_prediction_id, run_id


def create_app(data_root: Path = DATA, copilot: LLMExplanationService | None = None) -> FastAPI:
    store = ArtifactStore(data_root)
    evidence = EvidenceEngine(store)
    expected = json.loads((data_root / "geometry/expected_regions.json").read_text(encoding="utf-8"))
    regions = [Region(
        region_id=f"imd-{int(item['id']):02d}", region_name=item["name"],
        geometry_id=f"imd-{int(item['id']):02d}", geometry_reference=f"/v1/regions/geojson#imd-{int(item['id']):02d}",
    ) for item in expected["regions"]]
    region_names = {item.region_id: item.region_name for item in regions}
    model_report_hash = sha256_file(store.report_path)
    prediction_hash = store.report["predictions"]["sha256"]
    copilot_service = copilot or LLMExplanationService.from_env(data_root)

    def provenance() -> dict:
        return {
            "prediction_artifact_sha256": prediction_hash,
            "model_report_sha256": model_report_hash,
            "analog_scaler_sha256": evidence.analog_manifest["sha256"],
            "feature_contract": FEATURE_CONTRACT_VERSION,
            "forecast_source": "WeatherBench 2 official IFS ENS mean",
            "raw_ensemble_member_access": False,
        }

    def initialization_for(run: str) -> str:
        try:
            initialization = parse_run_id(run)
        except ValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not store.query("SELECT 1 FROM predictions WHERE forecast_initialization_time=? LIMIT 1", [initialization]):
            raise HTTPException(status_code=404, detail="Unknown run")
        return initialization

    app = FastAPI(
        title="Forecast Bust Detection API", version="1.0.0",
        description="Read-only historical-replay API for calibrated forecast-bust risk and deterministic evidence.",
    )
    cors_origins = [
        origin.strip() for origin in os.getenv(
            "FORECAST_BUST_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",") if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )

    @app.get("/health", response_model=HealthResponse, description="Core model and artifact readiness; independent of any optional copilot.")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", model_loaded=True, model_version=evidence.model_version, dataset_version=DATASET_VERSION)

    @app.get("/v1/model", response_model=ModelMetadata, description="Frozen model metadata and held-out 2022 evaluation metrics.")
    def model() -> ModelMetadata:
        report = store.report
        return ModelMetadata(
            model_version=report["model_version"], dataset_version=DATASET_VERSION,
            feature_contract=FEATURE_CONTRACT_VERSION, training_years=report["fit_years"],
            validation_year=report["validation_year"], test_year=report["test_year"],
            held_out_metrics=report["evaluations"]["test_2022"],
            prediction_semantics="forecast_confidence = forecast_reliability = 1.0 - bust_probability",
            calibration_method="sigmoid calibration fitted on 2021 classifier scores",
            provenance=provenance(),
        )

    @app.get("/v1/runs", response_model=list[ForecastRun], description="Available 2021–2022 historical replay initializations, newest first.")
    def runs() -> list[ForecastRun]:
        rows = store.query("""
            SELECT forecast_initialization_time, list_sort(list_distinct(list(lead_day))) AS lead_days, count(*) AS records
            FROM predictions GROUP BY forecast_initialization_time ORDER BY forecast_initialization_time DESC
        """)
        return [ForecastRun(
            run_id=run_id(item["forecast_initialization_time"]), source_forecast_time=item["forecast_initialization_time"],
            available_lead_days=[int(value) for value in item["lead_days"]], model_version=evidence.model_version,
            data_status="complete" if int(item["records"]) == 360 else "partial",
        ) for item in rows]

    @app.get("/v1/regions", response_model=list[Region], description="Canonical validated 36-region IMD subdivision manifest.")
    def get_regions() -> list[Region]:
        return regions

    @app.get("/v1/regions/geojson", response_class=FileResponse, description="Validated canonical 36-region GeoJSON in CRS84.")
    def region_geojson() -> FileResponse:
        path = data_root / "geometry/imd_subdivisions.geojson"
        if not path.exists():
            raise HTTPException(status_code=503, detail="Canonical region geometry artifact is missing")
        return FileResponse(path, media_type="application/geo+json", filename="imd_subdivisions.geojson")

    @app.get("/v1/risk-map", response_model=RiskMapResponse, description="Calibrated risk for all 36 regions at one replay run and lead day.")
    def risk_map(run_id_value: str = Query(alias="run_id"), lead_day: int = Query(ge=1, le=10)) -> RiskMapResponse:
        initialization = initialization_for(run_id_value)
        rows = store.prediction_rows(initialization, lead_day=lead_day)
        if not rows:
            raise HTTPException(status_code=404, detail="Prediction data is missing for the requested run and lead")
        if len(rows) != 36:
            raise HTTPException(status_code=409, detail="Prediction data is incomplete for the requested run and lead")
        items = []
        for row in rows:
            probability = float(row["bust_probability"])
            reliability = 1.0 - probability
            items.append(RegionRisk(
                prediction_id=make_prediction_id(evidence.model_version, row["forecast_initialization_time"], row["region_id"], int(row["lead_day"])),
                run_id=run_id_value, region_id=row["region_id"], region_name=row["region_name"], lead_day=int(row["lead_day"]),
                source_forecast_time=row["forecast_initialization_time"], valid_time=row["valid_time"],
                bust_probability=probability, forecast_confidence=reliability, forecast_reliability=reliability,
                model_version=evidence.model_version, dataset_version=row["dataset_version"], provenance=provenance(),
            ))
        return RiskMapResponse(run_id=run_id_value, lead_day=lead_day, risks=items)

    @app.get("/v1/regions/{region_id}/lead-curve", response_model=LeadCurveResponse, description="Day 1–10 calibrated risk curve for one subdivision and run.")
    def lead_curve(region_id: str, run_id_value: str = Query(alias="run_id")) -> LeadCurveResponse:
        if region_id not in region_names:
            raise HTTPException(status_code=404, detail="Unknown region")
        initialization = initialization_for(run_id_value)
        rows = store.prediction_rows(initialization, region_id=region_id)
        if len(rows) != 10:
            raise HTTPException(status_code=409 if rows else 404, detail="Lead-curve prediction data is incomplete or missing")
        points = [LeadRiskPoint(
            prediction_id=make_prediction_id(evidence.model_version, row["forecast_initialization_time"], region_id, int(row["lead_day"])),
            lead_day=int(row["lead_day"]), valid_time=row["valid_time"], bust_probability=float(row["bust_probability"]),
            forecast_reliability=1.0-float(row["bust_probability"]),
        ) for row in rows]
        return LeadCurveResponse(run_id=run_id_value, region_id=region_id, region_name=region_names[region_id], model_version=evidence.model_version, dataset_version=DATASET_VERSION, points=points)

    @app.get("/v1/predictions/{prediction_id}/explanation", response_model=PredictionExplanation, description="Deterministic TreeSHAP evidence and training-only historical analogs; no LLM.")
    def explanation(prediction_id: str) -> PredictionExplanation:
        try:
            identity = parse_prediction_id(prediction_id)
        except ValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if identity["model_version"] != evidence.model_version or identity["region_id"] not in region_names:
            raise HTTPException(status_code=404, detail="Unknown prediction")
        rows = store.prediction_rows(identity["source_forecast_time"], identity["lead_day"], identity["region_id"])
        if len(rows) != 1:
            raise HTTPException(status_code=404 if not rows else 409, detail="Prediction is missing or ambiguous")
        return evidence.explain(rows[0], provenance())

    @app.post("/v1/copilot/query", response_model=CopilotResponse, description="Optional grounded narrative over existing deterministic evidence; never performs prediction.")
    def copilot_query(payload: CopilotRequest, request: Request) -> CopilotResponse:
        try:
            identity = parse_prediction_id(payload.prediction_id)
        except ValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if identity["model_version"] != evidence.model_version or identity["region_id"] not in region_names:
            raise HTTPException(status_code=404, detail="Unknown prediction")
        rows = store.prediction_rows(identity["source_forecast_time"], identity["lead_day"], identity["region_id"])
        if len(rows) != 1:
            raise HTTPException(status_code=404 if not rows else 409, detail="Prediction is missing or ambiguous")
        deterministic_evidence = evidence.explain(rows[0], provenance())
        client_id = request.client.host if request.client else "unknown"
        return copilot_service.query(deterministic_evidence, payload, client_id)

    return app


app = create_app()
