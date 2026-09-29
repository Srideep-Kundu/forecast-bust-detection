import { useState } from 'react';
import { Database, ChevronDown } from 'lucide-react';
import type { ModelMetadata } from '../api/types';

const METRICS = [
  ['PR-AUC', 'pr_auc', 'Area under precision-recall curve (primary discrimination metric)'],
  ['ROC-AUC', 'roc_auc', 'Area under receiver operating characteristic curve'],
  ['Brier score', 'brier_score', 'Mean squared probability error (lower is better)'],
  ['Brier Skill Score', 'brier_skill_score', 'Improvement relative to climatology'],
  ['ECE', 'expected_calibration_error', 'Expected calibration error across bins'],
  ['Top-20%-risk recall', 'top_20_percent_risk_recall', 'Share of busts captured in highest risk quintile'],
] as const;

export function ModelInfoPanel({ model }: { model: ModelMetadata }) {
  const [isOpen, setIsOpen] = useState(false);
  const metrics = model.held_out_metrics.model;

  return (
    <aside className="model-panel bg-white rounded-xl border border-[#1f2a1d]/10 overflow-hidden shadow-sm" aria-label="Model information">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full p-4 flex items-center justify-between text-left hover:bg-[#f8faf7] transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-[#336443]" />
          <span className="text-sm font-semibold text-[#1f2a1d]">
            Model and held-out evaluation
          </span>
        </div>
        <ChevronDown className={`w-4 h-4 text-[#4b5b47] transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="p-5 border-t border-[#1f2a1d]/10 bg-[#fdfdfd] flex flex-col gap-5">
          <dl className="model-facts grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
            <div className="p-2.5 rounded bg-[#f8faf7] border border-[#1f2a1d]/5">
              <dt className="text-[#4b5b47]">Model</dt>
              <dd className="font-mono font-medium text-[#1f2a1d] mt-0.5">{model.model_version}</dd>
            </div>
            <div className="p-2.5 rounded bg-[#f8faf7] border border-[#1f2a1d]/5">
              <dt className="text-[#4b5b47]">Feature contract</dt>
              <dd className="font-mono font-medium text-[#1f2a1d] mt-0.5">{model.feature_contract}</dd>
            </div>
            <div className="p-2.5 rounded bg-[#f8faf7] border border-[#1f2a1d]/5">
              <dt className="text-[#4b5b47]">Dataset</dt>
              <dd className="font-mono font-medium text-[#1f2a1d] mt-0.5">{model.dataset_version}</dd>
            </div>
            <div className="p-2.5 rounded bg-[#f8faf7] border border-[#1f2a1d]/5">
              <dt className="text-[#4b5b47]">Fit</dt>
              <dd className="font-mono font-medium text-[#1f2a1d] mt-0.5">{model.training_years.join('–')}</dd>
            </div>
            <div className="p-2.5 rounded bg-[#f8faf7] border border-[#1f2a1d]/5">
              <dt className="text-[#4b5b47]">Validate / calibrate</dt>
              <dd className="font-mono font-medium text-[#1f2a1d] mt-0.5">{model.validation_year}</dd>
            </div>
            <div className="p-2.5 rounded bg-[#f8faf7] border border-[#1f2a1d]/5">
              <dt className="text-[#4b5b47]">Held-out test</dt>
              <dd className="font-mono font-medium text-[#1f2a1d] mt-0.5">{model.test_year}</dd>
            </div>
          </dl>

          <div className="metric-strip">
            <span className="text-[11px] font-mono uppercase tracking-wider text-[#85AB8B] block mb-2">
              Verification Metrics
            </span>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
              {METRICS.map(([label, key, description]) => {
                const value = metrics[key];
                return (
                  <div key={key} title={description} className="p-2.5 rounded bg-[#eef4ed]/50 border border-[#336443]/15 text-center">
                    <span className="text-[11px] text-[#4b5b47] block truncate">{label}</span>
                    <strong className="text-sm font-mono font-semibold text-[#1f2a1d] block mt-1">
                      {typeof value === 'number' ? value.toFixed(4) : '—'}
                    </strong>
                  </div>
                );
              })}
            </div>
          </div>

          <p className="helper-text text-[11px] text-[#4b5b47]">
            Metrics are loaded from the versioned 2022 evaluation artifact. PR-AUC is the primary discrimination metric.
          </p>
        </div>
      )}
    </aside>
  );
}
