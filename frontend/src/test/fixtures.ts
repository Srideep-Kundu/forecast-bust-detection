import type {
  ForecastRun,
  CopilotResponse,
  LeadCurveResponse,
  ModelMetadata,
  PredictionExplanation,
  Region,
  RegionGeometryCollection,
  RiskMapResponse,
} from '../api/types';

export const runId = 'run-20220930T120000Z';
export const modelVersion = 'xgb-bust-v2-mean-only';
export const datasetVersion = 'wb2-ifs-mean-india-v2';

export const runs: ForecastRun[] = [{
  run_id: runId,
  source_forecast_time: '2022-09-30T12:00:00.000000000',
  available_lead_days: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
  model_version: modelVersion,
  data_status: 'complete',
}];

export const regions: Region[] = Array.from({ length: 36 }, (_, index) => ({
  region_id: `imd-${String(index + 1).padStart(2, '0')}`,
  region_name: index === 0 ? 'Lakshadweep' : `Test Region ${index + 1}`,
  geometry_id: `imd-${String(index + 1).padStart(2, '0')}`,
  geometry_reference: `/v1/regions/geojson#imd-${String(index + 1).padStart(2, '0')}`,
}));

export const geometry: RegionGeometryCollection = {
  type: 'FeatureCollection',
  features: regions.map((region, index) => ({
    type: 'Feature',
    properties: { region_id: index + 1, region_name: region.region_name },
    geometry: { type: 'Polygon', coordinates: [[[70 + index * 0.01, 10], [70.005 + index * 0.01, 10], [70.005 + index * 0.01, 10.005], [70 + index * 0.01, 10]]] },
  })),
};

export function riskResponse(leadDay = 1): RiskMapResponse {
  return {
    run_id: runId,
    lead_day: leadDay,
    risks: regions.map((region, index) => {
      const probability = Math.min(0.98, 0.02 + index * 0.02 + leadDay * 0.005);
      return {
        prediction_id: `${modelVersion}__20220930T120000Z__${region.region_id}__d${String(leadDay).padStart(2, '0')}`,
        run_id: runId,
        region_id: region.region_id,
        region_name: region.region_name,
        lead_day: leadDay,
        source_forecast_time: '2022-09-30T12:00:00.000000000',
        valid_time: `2022-10-${String(leadDay + 1).padStart(2, '0')}T12:00:00.000000000`,
        bust_probability: probability,
        forecast_confidence: 1 - probability,
        forecast_reliability: 1 - probability,
        model_version: modelVersion,
        dataset_version: datasetVersion,
        provenance: { raw_ensemble_member_access: false },
      };
    }),
  };
}

export function leadCurve(regionId = 'imd-01'): LeadCurveResponse {
  const region = regions.find((item) => item.region_id === regionId) ?? regions[0];
  return {
    run_id: runId,
    region_id: region.region_id,
    region_name: region.region_name,
    model_version: modelVersion,
    dataset_version: datasetVersion,
    points: Array.from({ length: 10 }, (_, index) => ({
      prediction_id: `${modelVersion}__20220930T120000Z__${region.region_id}__d${String(index + 1).padStart(2, '0')}`,
      lead_day: index + 1,
      valid_time: `2022-10-${String(index + 2).padStart(2, '0')}T12:00:00.000000000`,
      bust_probability: 0.05 + index * 0.03,
      forecast_reliability: 0.95 - index * 0.03,
    })),
  };
}

export function explanation(regionId = 'imd-01', leadDay = 1): PredictionExplanation {
  const region = regions.find((item) => item.region_id === regionId) ?? regions[0];
  const probability = riskResponse(leadDay).risks.find((item) => item.region_id === region.region_id)!.bust_probability;
  return {
    prediction_id: `${modelVersion}__20220930T120000Z__${region.region_id}__d${String(leadDay).padStart(2, '0')}`,
    run_id: runId,
    region_id: region.region_id,
    region_name: region.region_name,
    lead_day: leadDay,
    source_forecast_time: '2022-09-30T12:00:00.000000000',
    valid_time: '2022-10-01T12:00:00.000000000',
    raw_model_output: 0.03,
    bust_probability: probability,
    forecast_reliability: 1 - probability,
    model_version: modelVersion,
    dataset_version: datasetVersion,
    base_value: -2.1,
    top_positive_drivers: [{ feature_name: 'thickness500_850_m', display_name: '500–850 hPa Thickness', value: 4321, unit: 'm', shap_value: 0.247, direction: 'increased', interpretation: "This feature increased the model's predicted bust risk." }],
    top_negative_drivers: [{ feature_name: 'precip24_mean_mm', display_name: '24-hour Precipitation', value: 2.4, unit: 'mm', shap_value: -2.312, direction: 'decreased', interpretation: "This feature decreased the model's predicted bust risk." }],
    feature_values: [],
    historical_analogs: [{
      initialization_time: '2020-08-14T12:00:00.000000000',
      valid_time: '2020-08-15T12:00:00.000000000',
      region_id: region.region_id,
      region_name: region.region_name,
      lead_day: 1,
      distance: 1.284,
      bust: 1,
      severity: 2.1,
      forecast_feature_summary: { precip24_mean_mm: 2.2 },
      retrospective_error_summary: { e_precip_mm: 18.4, e_wind_mps: 4.2 },
      dataset_version: datasetVersion,
    }],
    provenance: { raw_ensemble_member_access: false },
  };
}

export const model: ModelMetadata = {
  model_version: modelVersion,
  dataset_version: datasetVersion,
  feature_contract: 'mean-only-mvp-v2',
  training_years: [2018, 2019, 2020],
  validation_year: 2021,
  test_year: 2022,
  held_out_metrics: { model: { pr_auc: 0.754087, roc_auc: 0.9164, brier_score: 0.0766, brier_skill_score: 0.4486, expected_calibration_error: 0.0253, top_20_percent_risk_recall: 0.7269 } },
  prediction_semantics: 'forecast_confidence = forecast_reliability = 1.0 - bust_probability',
  calibration_method: 'sigmoid calibration fitted on 2021 classifier scores',
  provenance: {},
};

export function copilotResponse(
  regionId = 'imd-01',
  leadDay = 1,
  degraded = false,
): CopilotResponse {
  const evidence = explanation(regionId, leadDay);
  return {
    answer: degraded
      ? 'The calibrated bust probability is grounded in the deterministic model evidence.'
      : 'The supplied SHAP evidence shows that 500–850 hPa Thickness increased the model prediction.',
    prediction_id: evidence.prediction_id,
    region_id: regionId,
    region_name: evidence.region_name,
    lead_day: leadDay,
    model_version: modelVersion,
    dataset_version: datasetVersion,
    llm_provider: degraded ? 'deterministic-fallback' : 'gemini',
    llm_model: 'test-gemini',
    prompt_version: 'copilot-v1',
    grounding_sources: ['bust_probability', 'forecast_reliability', 'top_positive_shap_drivers', 'historical_analog_summaries'],
    generated_at: '2026-09-29T10:00:00Z',
    cached: false,
    degraded,
    degradation_reason: degraded ? 'llm_disabled' : null,
    disclaimer: 'AI-generated explanation based only on deterministic evidence.',
  };
}
