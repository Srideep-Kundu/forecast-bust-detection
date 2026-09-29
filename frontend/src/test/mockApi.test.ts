import { afterEach, describe, expect, it, vi } from 'vitest';
import { installMockApi } from './mockApi';

afterEach(() => vi.restoreAllMocks());

describe('contract fixture transport', () => {
  it('returns lead-curve and explanation JSON through the fetch boundary', async () => {
    installMockApi();
    const curve = await fetch('http://localhost:8000/v1/regions/imd-01/lead-curve?run_id=run-20220930T120000Z');
    const evidence = await fetch('http://localhost:8000/v1/predictions/xgb-bust-v2-mean-only__20220930T120000Z__imd-01__d01/explanation');
    expect((await curve.json()).points).toHaveLength(10);
    expect((await evidence.json()).historical_analogs).toHaveLength(1);
  });
});
