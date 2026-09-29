import { Activity } from 'lucide-react';
import type { PredictionExplanation } from '../api/types';
import { HistoricalAnalogs } from './HistoricalAnalogs';
import { ShapDrivers } from './ShapDrivers';
import { CopilotPanel } from './CopilotPanel';

export function ExplanationPanel({ explanation }: { explanation: PredictionExplanation }) {
  return (
    <section className="evidence-panel bg-white rounded-xl border border-[#1f2a1d]/10 p-6 shadow-sm flex flex-col" aria-labelledby="evidence-title">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 mb-4 border-b border-[#1f2a1d]/10">
        <div className="flex flex-col">
          <span className="text-[11px] font-mono uppercase tracking-wider text-[#85AB8B] flex items-center gap-1">
            <Activity className="w-3 h-3 text-[#336443]" />
            Deterministic model evidence
          </span>
          <h2 id="evidence-title" className="text-xl font-semibold text-[#1f2a1d]">
            Why the model shifted this risk
          </h2>
        </div>
        <code className="text-[11px] font-mono bg-[#f8faf7] text-[#4b5b47] px-2.5 py-1 rounded border border-[#1f2a1d]/10 truncate max-w-xs" title={explanation.prediction_id}>
          {explanation.prediction_id}
        </code>
      </div>

      <p className="helper-text text-xs text-[#4b5b47] mb-6">
        SHAP values describe how model features shifted this prediction relative to the model baseline. They do not establish physical causation.
      </p>

      <ShapDrivers positive={explanation.top_positive_drivers} negative={explanation.top_negative_drivers} />
      <HistoricalAnalogs analogs={explanation.historical_analogs} />
      <CopilotPanel key={explanation.prediction_id} explanation={explanation} />
    </section>
  );
}
