import { Tag } from '@carbon/react';
import type { AnalogEvent } from '../api/types';
import { formatDateTime, formatFeatureName } from '../utils/format';

interface HistoricalAnalogsProps {
  analogs: AnalogEvent[];
}

export function HistoricalAnalogs({ analogs }: HistoricalAnalogsProps) {
  return (
    <section className="analog-panel" aria-labelledby="analogs-title">
      <div className="panel-heading">
        <div><span className="eyebrow">Retrospective evidence</span><h2 id="analogs-title">Similar historical forecast states</h2></div>
      </div>
      <p className="helper-text">Training-period comparisons only. These are not forecasts for the current replay event.</p>
      {analogs.length ? (
        <ol className="analog-list">
          {analogs.map((analog, index) => (
            <li key={`${analog.initialization_time}-${analog.lead_day}`}>
              <header>
                <span className="analog-list__rank">{String(index + 1).padStart(2, '0')}</span>
                <div><strong>{formatDateTime(analog.initialization_time)}</strong><small>Day {analog.lead_day} · distance {analog.distance.toFixed(2)}</small></div>
                <Tag type={analog.bust ? 'red' : 'green'} size="sm">Historical {analog.bust ? 'bust' : 'no bust'}</Tag>
              </header>
              <dl>
                {Object.entries(analog.retrospective_error_summary).slice(0, 4).map(([name, value]) => (
                  <div key={name}><dt>{formatFeatureName(name)}</dt><dd>{value.toFixed(2)}</dd></div>
                ))}
              </dl>
            </li>
          ))}
        </ol>
      ) : <p className="empty-copy">No eligible 2018–2020 analogs were returned.</p>}
    </section>
  );
}
