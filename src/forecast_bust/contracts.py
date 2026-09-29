from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: Literal["ok", "not_ready"]
    model_loaded: bool
    model_version: str
    dataset_version: str


class ForecastRun(BaseModel):
    run_id: str
    source_forecast_time: str
    available_lead_days: list[int]
    model_version: str
    data_status: Literal["complete", "partial"]


class Region(BaseModel):
    region_id: str
    region_name: str
    geometry_id: str
    geometry_reference: str


class RegionRisk(BaseModel):
    prediction_id: str
    run_id: str
    region_id: str
    region_name: str
    lead_day: int = Field(ge=1, le=10)
    source_forecast_time: str
    valid_time: str
    bust_probability: float = Field(ge=0, le=1)
    forecast_confidence: float = Field(ge=0, le=1)
    forecast_reliability: float = Field(ge=0, le=1)
    model_version: str
    dataset_version: str
    provenance: dict[str, Any]


class RiskMapResponse(BaseModel):
    run_id: str
    lead_day: int
    risks: list[RegionRisk]


class LeadRiskPoint(BaseModel):
    prediction_id: str
    lead_day: int = Field(ge=1, le=10)
    valid_time: str
    bust_probability: float = Field(ge=0, le=1)
    forecast_reliability: float = Field(ge=0, le=1)


class LeadCurveResponse(BaseModel):
    run_id: str
    region_id: str
    region_name: str
    model_version: str
    dataset_version: str
    points: list[LeadRiskPoint]


class FeatureValue(BaseModel):
    feature_name: str
    display_name: str
    value: float | int | str
    unit: str | None


class ShapDriver(FeatureValue):
    shap_value: float
    direction: Literal["increased", "decreased"]
    interpretation: str


class AnalogEvent(BaseModel):
    initialization_time: str
    valid_time: str
    region_id: str
    region_name: str
    lead_day: int
    distance: float = Field(ge=0)
    bust: int = Field(ge=0, le=1)
    severity: float
    forecast_feature_summary: dict[str, float]
    retrospective_error_summary: dict[str, float]
    dataset_version: str


class PredictionExplanation(BaseModel):
    prediction_id: str
    run_id: str
    region_id: str
    region_name: str
    lead_day: int
    source_forecast_time: str
    valid_time: str
    raw_model_output: float
    bust_probability: float = Field(ge=0, le=1)
    forecast_reliability: float = Field(ge=0, le=1)
    model_version: str
    dataset_version: str
    base_value: float
    top_positive_drivers: list[ShapDriver]
    top_negative_drivers: list[ShapDriver]
    feature_values: list[FeatureValue]
    historical_analogs: list[AnalogEvent]
    provenance: dict[str, Any]


class ModelMetadata(BaseModel):
    model_version: str
    dataset_version: str
    feature_contract: str
    training_years: list[int]
    validation_year: int
    test_year: int
    held_out_metrics: dict[str, Any]
    prediction_semantics: str
    calibration_method: str
    provenance: dict[str, Any]


class CopilotRequest(BaseModel):
    prediction_id: str = Field(min_length=1, max_length=180)
    question: str = Field(min_length=1, max_length=500)
    explanation_mode: Literal["simple", "meteorological"] = "simple"

    @field_validator("prediction_id", "question")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class CopilotFeatureValue(BaseModel):
    feature_name: str
    display_name: str
    value: float | int | str
    unit: str | None


class CopilotShapDriver(CopilotFeatureValue):
    shap_value: float
    direction: Literal["increased", "decreased"]


class CopilotAnalogSummary(BaseModel):
    initialization_time: str
    valid_time: str
    lead_day: int = Field(ge=1, le=10)
    distance: float = Field(ge=0)
    historical_bust: bool


class CopilotProvenance(BaseModel):
    prediction_artifact_sha256: str | None = None
    model_report_sha256: str | None = None
    analog_scaler_sha256: str | None = None
    feature_contract: str | None = None
    forecast_source: str | None = None
    raw_ensemble_member_access: bool = False


class CopilotContext(BaseModel):
    prediction_id: str
    run_id: str
    region_id: str
    region_name: str
    lead_day: int = Field(ge=1, le=10)
    source_forecast_time: str
    valid_time: str
    bust_probability: float = Field(ge=0, le=1)
    forecast_reliability: float = Field(ge=0, le=1)
    model_version: str
    dataset_version: str
    top_positive_shap_drivers: list[CopilotShapDriver]
    top_negative_shap_drivers: list[CopilotShapDriver]
    approved_feature_values: list[CopilotFeatureValue]
    historical_analog_summaries: list[CopilotAnalogSummary]
    run_to_run_drift: CopilotFeatureValue | None
    provenance: CopilotProvenance
    explanation_mode: Literal["simple", "meteorological"]


class CopilotResponse(BaseModel):
    answer: str
    prediction_id: str
    region_id: str
    region_name: str
    lead_day: int = Field(ge=1, le=10)
    model_version: str
    dataset_version: str
    llm_provider: str
    llm_model: str
    prompt_version: str
    grounding_sources: list[str]
    generated_at: str
    cached: bool
    degraded: bool
    degradation_reason: str | None
    disclaimer: str
