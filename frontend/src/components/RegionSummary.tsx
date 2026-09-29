import { Tag } from '@carbon/react';
import type { RegionRisk } from '../api/types';
import { formatDateTime, formatProbability } from '../utils/format';

interface RegionSummaryProps {
  risk?: RegionRisk;
}

export function RegionSummary({ risk }: RegionSummaryProps) {
  if (!risk) {
    return <div className="region-summary region-summary--empty">Select a subdivision to inspect its Day 1–10 evidence.</div>;
  }

  return (
    <section className="region-summary" aria-labelledby="region-summary-title">
      <div>
        <span className="eyebrow">Selected subdivision</span>
        <h2 id="region-summary-title">{risk.region_name}</h2>
        <p>{formatDateTime(risk.source_forecast_time)} initialization · Day {risk.lead_day} · valid {formatDateTime(risk.valid_time)}</p>
      </div>
      <dl className="region-summary__metrics">
        <div>
          <dt>Bust probability</dt>
          <dd>{formatProbability(risk.bust_probability)}</dd>
        </div>
        <div>
          <dt>Forecast Reliability</dt>
          <dd>{formatProbability(risk.forecast_confidence)}</dd>
        </div>
      </dl>
      <Tag type="outline" size="sm">Calibrated probability</Tag>
      <p className="helper-text">Forecast Reliability = 1 - predicted probability of a forecast bust.</p>
    </section>
  );
}
