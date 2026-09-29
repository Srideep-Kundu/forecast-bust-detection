import { History, CheckCircle2, AlertCircle } from 'lucide-react';
import type { AnalogEvent } from '../api/types';
import { formatDateTime, formatFeatureName } from '../utils/format';

interface HistoricalAnalogsProps {
  analogs: AnalogEvent[];
}

export function HistoricalAnalogs({ analogs }: HistoricalAnalogsProps) {
  return (
    <section className="mt-8 pt-6 border-t border-[#1f2a1d]/10" aria-labelledby="analogs-title">
      <div className="flex flex-col mb-4">
        <span className="text-[11px] font-mono uppercase tracking-wider text-[#85AB8B] flex items-center gap-1">
          <History className="w-3 h-3 text-[#336443]" />
          Retrospective evidence
        </span>
        <h2 id="analogs-title" className="text-base font-semibold text-[#1f2a1d]">
          Similar historical forecast states
        </h2>
        <p className="text-xs text-[#4b5b47] mt-0.5">
          Training-period comparisons only. These are not forecasts for the current replay event.
        </p>
      </div>

      {analogs.length ? (
        <ol className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {analogs.map((analog, index) => {
            const isBust = analog.bust;
            return (
              <li
                key={`${analog.initialization_time}-${analog.lead_day}`}
                className="bg-[#f8faf7] rounded-lg border border-[#1f2a1d]/10 p-3.5 flex flex-col justify-between gap-3 text-xs"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded bg-[#1f2a1d] text-white flex items-center justify-center font-mono font-medium text-[11px]">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <div>
                      <strong className="text-[#1f2a1d] block font-medium">
                        {formatDateTime(analog.initialization_time)}
                      </strong>
                      <span className="text-[11px] text-[#4b5b47] font-mono">
                        Day {analog.lead_day} · distance {analog.distance.toFixed(2)}
                      </span>
                    </div>
                  </div>

                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium text-[11px] border ${
                    isBust
                      ? 'bg-amber-100/70 text-[#8c3b24] border-amber-300'
                      : 'bg-[#eef4ed] text-[#336443] border-[#336443]/30'
                  }`}>
                    {isBust ? <AlertCircle className="w-3 h-3" /> : <CheckCircle2 className="w-3 h-3" />}
                    Historical {isBust ? 'bust' : 'no bust'}
                  </span>
                </div>

                <dl className="grid grid-cols-2 gap-1.5 pt-2 border-t border-[#1f2a1d]/5 text-[11px]">
                  {Object.entries(analog.retrospective_error_summary).slice(0, 4).map(([name, value]) => (
                    <div key={name} className="flex justify-between bg-white px-2 py-1 rounded border border-[#1f2a1d]/5">
                      <dt className="text-[#4b5b47] truncate max-w-[90px]">{formatFeatureName(name)}</dt>
                      <dd className="font-mono font-medium text-[#1f2a1d]">{value.toFixed(2)}</dd>
                    </div>
                  ))}
                </dl>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="text-xs text-[#4b5b47] italic">No eligible 2018–2020 analogs were returned.</p>
      )}
    </section>
  );
}
