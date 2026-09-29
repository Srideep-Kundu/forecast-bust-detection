import { Calendar, Clock, SlidersHorizontal } from 'lucide-react';
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
      <section className="bg-white rounded-xl border border-[#1f2a1d]/10 p-5 mb-6 animate-pulse flex flex-col md:flex-row gap-4 items-center justify-between" aria-label="Forecast controls" aria-busy="true">
        <div className="h-6 bg-[#eef4ed] rounded w-64" />
        <div className="flex gap-4 w-full md:w-auto">
          <div className="h-10 bg-[#eef4ed] rounded w-48" />
          <div className="h-10 bg-[#eef4ed] rounded w-36" />
        </div>
      </section>
    );
  }

  return (
    <section className="bg-white rounded-xl border border-[#1f2a1d]/10 p-5 mb-6 shadow-sm flex flex-col lg:flex-row gap-6 lg:items-center lg:justify-between" aria-label="Forecast controls">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[#85AB8B]">
          <SlidersHorizontal className="w-3.5 h-3.5 text-[#336443]" />
          <span>Diagnostic Controls</span>
        </div>
        <h2 className="text-xl font-medium text-[#1f2a1d] tracking-tight">
          Explore Calibrated Forecast-Bust Risk
        </h2>
        <p className="text-xs text-[#4b5b47]">
          Select an initialized model run and advance the forecast lead horizon from Day 1 through Day 10.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="forecast-run" className="text-xs font-medium text-[#4b5b47] flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5 text-[#336443]" />
            <span>Forecast run</span>
          </label>
          <select
            id="forecast-run"
            aria-label="Forecast run"
            value={runId}
            onChange={(event) => onRunChange(event.target.value)}
            disabled={!runs?.length}
            className="bg-[#f8faf7] hover:bg-[#eef4ed] focus:bg-white text-[#1f2a1d] text-sm font-medium px-3.5 py-2 rounded-lg border border-[#1f2a1d]/15 focus:border-[#336443] focus:ring-1 focus:ring-[#336443] transition-colors outline-none cursor-pointer"
          >
            {!runs?.length ? <option value="">No runs available</option> : null}
            {runs?.map((run) => (
              <option key={run.run_id} value={run.run_id}>
                {formatDateTime(run.source_forecast_time)} {run.data_status === 'partial' ? '(partial)' : ''}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="lead-day" className="text-xs font-medium text-[#4b5b47] flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-[#336443]" />
            <span>Lead day</span>
          </label>
          <select
            id="lead-day"
            aria-label="Lead day"
            value={String(leadDay)}
            onChange={(event) => onLeadChange(Number(event.target.value))}
            className="bg-[#f8faf7] hover:bg-[#eef4ed] focus:bg-white text-[#1f2a1d] text-sm font-medium px-3.5 py-2 rounded-lg border border-[#1f2a1d]/15 focus:border-[#336443] focus:ring-1 focus:ring-[#336443] transition-colors outline-none cursor-pointer"
          >
            {Array.from({ length: 10 }, (_, index) => index + 1).map((day) => (
              <option key={day} value={String(day)}>
                Day {day} (+{day * 24}h)
              </option>
            ))}
          </select>
        </div>
      </div>
    </section>
  );
}
