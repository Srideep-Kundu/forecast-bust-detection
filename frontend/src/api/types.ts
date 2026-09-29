import type { FeatureCollection, Geometry } from 'geojson';

export interface HealthResponse {
  status: 'ok' | 'not_ready';
  model_loaded: boolean;
  model_version: string;
  dataset_version: string;
}

export interface ForecastRun {
  run_id: string;
  source_forecast_time: string;
  available_lead_days: number[];
  model_version: string;
  data_status: 'complete' | 'partial';
}

export interface Region {
  region_id: string;
  region_name: string;
  geometry_id: string;
  geometry_reference: string;
}

export interface Provenance {
  prediction_artifact_sha256?: string;
  model_report_sha256?: string;
  analog_scaler_sha256?: string;
  feature_contract?: string;
  forecast_source?: string;
  raw_ensemble_member_access?: boolean;
  [key: string]: unknown;
}

export interface RegionRisk {
  prediction_id: string;
  run_id: string;
  region_id: string;
  region_name: string;
  lead_day: number;
  source_forecast_time: string;
  valid_time: string;
  bust_probability: number;
  forecast_confidence: number;
  forecast_reliability: number;
  model_version: string;
  dataset_version: string;
  provenance: Provenance;
}

export interface RiskMapResponse {
  run_id: string;
  lead_day: number;
  risks: RegionRisk[];
}

export interface LeadRiskPoint {
  prediction_id: string;
  lead_day: number;
  valid_time: string;
  bust_probability: number;
  forecast_reliability: number;
}

export interface LeadCurveResponse {
  run_id: string;
  region_id: string;
  region_name: string;
  model_version: string;
  dataset_version: string;
  points: LeadRiskPoint[];
}

export interface FeatureValue {
  feature_name: string;
  display_name: string;
  value: number | string;
  unit: string | null;
}

export interface ShapDriver extends FeatureValue {
  shap_value: number;
  direction: 'increased' | 'decreased';
  interpretation: string;
}

export interface AnalogEvent {
  initialization_time: string;
  valid_time: string;
  region_id: string;
  region_name: string;
  lead_day: number;
  distance: number;
  bust: 0 | 1;
  severity: number;
  forecast_feature_summary: Record<string, number>;
  retrospective_error_summary: Record<string, number>;
  dataset_version: string;
}

export interface PredictionExplanation {
  prediction_id: string;
  run_id: string;
  region_id: string;
  region_name: string;
  lead_day: number;
  source_forecast_time: string;
  valid_time: string;
  raw_model_output: number;
  bust_probability: number;
  forecast_reliability: number;
  model_version: string;
  dataset_version: string;
  base_value: number;
  top_positive_drivers: ShapDriver[];
  top_negative_drivers: ShapDriver[];
  feature_values: FeatureValue[];
  historical_analogs: AnalogEvent[];
  provenance: Provenance;
}

export interface EvaluationMetricSet {
  pr_auc?: number;
  roc_auc?: number;
  brier_score?: number;
  brier_skill_score?: number;
  expected_calibration_error?: number;
  top_20_percent_risk_recall?: number | null;
  [key: string]: unknown;
}

export interface ModelMetadata {
  model_version: string;
  dataset_version: string;
  feature_contract: string;
  training_years: number[];
  validation_year: number;
  test_year: number;
  held_out_metrics: { model: EvaluationMetricSet; [key: string]: unknown };
  prediction_semantics: string;
  calibration_method: string;
  provenance: Provenance;
}

export interface CopilotRequest {
  prediction_id: string;
  question: string;
  explanation_mode?: 'simple' | 'meteorological';
}

export interface CopilotResponse {
  answer: string;
  prediction_id: string;
  region_id: string;
  region_name: string;
  lead_day: number;
  model_version: string;
  dataset_version: string;
  llm_provider: string;
  llm_model: string;
  prompt_version: string;
  grounding_sources: string[];
  generated_at: string;
  cached: boolean;
  degraded: boolean;
  degradation_reason: string | null;
  disclaimer: string;
}

export type RegionGeometryCollection = FeatureCollection<Geometry, {
  region_id: number | string;
  region_name: string;
  [key: string]: unknown;
}>;
