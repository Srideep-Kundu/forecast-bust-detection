import { Select, SelectItem, SkeletonText } from '@carbon/react';
import type { ForecastRun } from '../api/types';
import { formatDateTime } from '../utils/format';

interface ControlBarProps {
  runs?: ForecastRun[];
  runId: string;
  leadDay: number;
  onRunChange: (runId: string) => void;
  onLeadChange: (lead: number) => void;
  loading: boolean;
}

export function ControlBar({ runs, runId, leadDay, onRunChange, onLeadChange, loading }: ControlBarProps) {
  if (loading) {
    return (
      <section className="control-bar" aria-label="Forecast controls" aria-busy="true">
        <div className="control-skeleton"><SkeletonText heading /><SkeletonText /></div>
        <div className="control-skeleton"><SkeletonText heading /><SkeletonText /></div>
      </section>
    );
  }

  return (
    <section className="control-bar" aria-label="Forecast controls">
      <div className="control-bar__intro">
        <span className="eyebrow">Historical Replay</span>
        <strong>Explore calibrated forecast-bust risk</strong>
      </div>
      <Select
        id="forecast-run"
        labelText="Forecast run"
        value={runId}
        onChange={(event) => onRunChange(event.target.value)}
        disabled={!runs?.length}
      >
        {!runs?.length ? <SelectItem value="" text="No runs available" /> : null}
        {runs?.map((run) => (
          <SelectItem
            key={run.run_id}
            value={run.run_id}
            text={`${formatDateTime(run.source_forecast_time)}${run.data_status === 'partial' ? ' · partial' : ''}`}
          />
        ))}
      </Select>
      <Select
        id="lead-day"
        labelText="Lead day"
        value={String(leadDay)}
        onChange={(event) => onLeadChange(Number(event.target.value))}
      >
        {Array.from({ length: 10 }, (_, index) => index + 1).map((day) => (
          <SelectItem key={day} value={String(day)} text={`Day ${day} · +${day * 24}h`} />
        ))}
      </Select>
    </section>
  );
}
