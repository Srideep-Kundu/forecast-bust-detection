export function formatProbability(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatContribution(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(3)}`;
}

export function formatDateTime(value: string): string {
  // Backend replay timestamps are UTC-naive ISO strings with nanosecond precision.
  // Normalize them explicitly so browsers never reinterpret them in the host timezone.
  const millisecondPrecision = value.replace(/(\.\d{3})\d+/, '$1');
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(millisecondPrecision)
    ? millisecondPrecision
    : `${millisecondPrecision}Z`;
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
    timeZoneName: 'short',
  }).format(new Date(normalized));
}

export function formatFeatureName(value: string): string {
  return value
    .replaceAll('_', ' ')
    .replace(/\b(mslp|mm|mps|pa|k)\b/gi, (part) => part.toUpperCase());
}
