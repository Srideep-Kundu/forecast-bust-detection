import type {
  ForecastRun,
  CopilotRequest,
  CopilotResponse,
  HealthResponse,
  LeadCurveResponse,
  ModelMetadata,
  PredictionExplanation,
  Region,
  RegionGeometryCollection,
  RiskMapResponse,
} from './types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...init?.headers },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Preserve the typed status when the server does not return JSON.
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>('/health'),
  model: () => request<ModelMetadata>('/v1/model'),
  runs: () => request<ForecastRun[]>('/v1/runs'),
  regions: () => request<Region[]>('/v1/regions'),
  geometry: () => request<RegionGeometryCollection>('/v1/regions/geojson'),
  riskMap: (runId: string, leadDay: number) =>
    request<RiskMapResponse>(`/v1/risk-map?run_id=${encodeURIComponent(runId)}&lead_day=${leadDay}`),
  leadCurve: (runId: string, regionId: string) =>
    request<LeadCurveResponse>(`/v1/regions/${encodeURIComponent(regionId)}/lead-curve?run_id=${encodeURIComponent(runId)}`),
  explanation: (predictionId: string) =>
    request<PredictionExplanation>(`/v1/predictions/${encodeURIComponent(predictionId)}/explanation`),
  copilot: (body: CopilotRequest) => request<CopilotResponse>('/v1/copilot/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
};
