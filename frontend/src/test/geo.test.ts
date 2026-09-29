import { describe, expect, it } from 'vitest';
import { geometry, riskResponse } from './fixtures';
import { joinRiskGeoJson } from '../utils/geo';

describe('risk-map data transformation', () => {
  it('joins all 36 geometries to canonical risk records without changing probabilities', () => {
    const risks = riskResponse(7).risks;
    const joined = joinRiskGeoJson(geometry, risks);

    expect(joined.features).toHaveLength(36);
    expect(joined.features[0].properties.canonical_region_id).toBe('imd-01');
    expect(joined.features[0].properties.bust_probability).toBe(risks[0].bust_probability);
    expect(joined.features[0].properties.forecast_confidence).toBe(risks[0].forecast_confidence);
    expect(joined.features[35].properties.canonical_region_id).toBe('imd-36');
  });
});
