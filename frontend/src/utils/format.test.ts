import { describe, expect, it } from 'vitest';
import { formatDateTime } from './format';

describe('formatDateTime', () => {
  it('treats UTC-naive backend timestamps as UTC', () => {
    const formatted = formatDateTime('2022-09-30T12:00:00.000000000');
    expect(formatted).toContain('12:00');
    expect(formatted).toContain('UTC');
  });
});
