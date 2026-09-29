import { copilotResponse, datasetVersion, explanation, geometry, leadCurve, model, modelVersion, regions, riskResponse, runs } from './fixtures';
import { vi } from 'vitest';

export function installMockApi(options: {
  emptyRuns?: boolean;
  failRisk?: boolean;
  delayExplanation?: boolean;
  failExplanation?: boolean;
  delayCopilot?: boolean;
  failCopilot?: boolean;
  degradedCopilot?: boolean;
} = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/health')) return json({ status: 'ok', model_loaded: true, model_version: modelVersion, dataset_version: datasetVersion });
    if (url.endsWith('/v1/model')) return json(model);
    if (url.endsWith('/v1/runs')) return json(options.emptyRuns ? [] : runs);
    if (url.endsWith('/v1/regions')) return json(regions);
    if (url.endsWith('/v1/regions/geojson')) return json(geometry);
    if (url.endsWith('/v1/copilot/query')) {
      if (options.delayCopilot) return new Promise<Response>(() => undefined);
      if (options.failCopilot) return json({ detail: 'Provider unavailable' }, 503);
      const body = JSON.parse(String(init?.body)) as { prediction_id: string };
      const match = body.prediction_id.match(/__(imd-\d+)__d(\d+)$/);
      return json(copilotResponse(match?.[1] ?? 'imd-01', Number(match?.[2] ?? 1), options.degradedCopilot));
    }
    if (url.includes('/v1/risk-map')) {
      if (options.failRisk) return json({ detail: 'Risk artifact unavailable' }, 503);
      const lead = Number(new URL(url).searchParams.get('lead_day'));
      return json(riskResponse(lead));
    }
    const curveMatch = url.match(/\/v1\/regions\/(imd-\d+)\/lead-curve/);
    if (curveMatch) return json(leadCurve(curveMatch[1]));
    const predictionMatch = url.match(/__(imd-\d+)__d(\d+)\/explanation/);
    if (predictionMatch) {
      if (options.delayExplanation) return new Promise<Response>(() => undefined);
      if (options.failExplanation) return json({ detail: 'Explanation unavailable' }, 503);
      return json(explanation(predictionMatch[1], Number(predictionMatch[2])));
    }
    return json({ detail: `Unhandled mock URL ${url}` }, 404);
  });
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}
