import { MapPin, ShieldCheck, AlertTriangle } from 'lucide-react';
import type { RegionRisk } from '../api/types';
import { formatDateTime, formatProbability } from '../utils/format';

interface RegionSummaryProps {
  risk?: RegionRisk;
}

export function RegionSummary({ risk }: RegionSummaryProps) {
  if (!risk) {
    return (
      <div className="bg-white rounded-xl border border-[#1f2a1d]/10 p-6 mb-6 text-[#4b5b47] text-sm flex items-center gap-3">
        <MapPin className="w-4 h-4 text-[#85AB8B]" />
        <span>Select a subdivision to inspect its Day 1–10 evidence.</span>
      </div>
    );
  }

  const isHighRisk = (risk.bust_probability ?? 0) >= 0.5;

  return (
    <section className="bg-white rounded-xl border border-[#1f2a1d]/10 p-6 mb-6 shadow-sm flex flex-col md:flex-row gap-6 md:items-center justify-between" aria-labelledby="region-summary-title">
      <div className="flex flex-col gap-1 max-w-xl">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono uppercase tracking-wider text-[#85AB8B] flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-[#336443]" />
            Selected subdivision
          </span>
          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${
            isHighRisk
              ? 'bg-amber-50 text-[#8c3b24] border-[#8c3b24]/20'
              : 'bg-[#eef4ed] text-[#336443] border-[#336443]/20'
          }`}>
            {isHighRisk ? <AlertTriangle className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
            {isHighRisk ? 'Elevated Bust Risk' : 'Calibrated probability'}
          </span>
        </div>
        <h2 id="region-summary-title" className="text-2xl font-semibold text-[#1f2a1d] tracking-tight">
          {risk.region_name}
        </h2>
        <p className="text-xs text-[#4b5b47]">
          {formatDateTime(risk.source_forecast_time)} initialization · Day {risk.lead_day} · valid {formatDateTime(risk.valid_time)}
        </p>
      </div>

      <div className="flex items-center gap-4 sm:gap-6 border-t md:border-t-0 md:border-l border-[#1f2a1d]/10 pt-4 md:pt-0 md:pl-6">
        <div className="flex flex-col">
          <span className="text-xs text-[#4b5b47] font-medium">Bust probability</span>
          <span className="text-2xl font-semibold font-mono text-[#1f2a1d]">
            {formatProbability(risk.bust_probability)}
          </span>
          <span className="text-[11px] text-[#85AB8B]">Calibrated output</span>
        </div>

        <div className="flex flex-col">
          <span className="text-xs text-[#4b5b47] font-medium">Forecast Reliability</span>
          <span className="text-2xl font-semibold font-mono text-[#336443]">
            {formatProbability(risk.forecast_confidence)}
          </span>
          <span className="text-[11px] text-[#4b5b47]">1 - P(bust)</span>
        </div>
      </div>
    </section>
  );
}
