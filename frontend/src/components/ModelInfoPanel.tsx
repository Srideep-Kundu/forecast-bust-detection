import { Accordion, AccordionItem, DefinitionTooltip } from '@carbon/react';
import type { ModelMetadata } from '../api/types';

const METRICS = [
  ['PR-AUC', 'pr_auc', 'Area under the precision-recall curve; primary discrimination metric.'],
  ['ROC-AUC', 'roc_auc', 'Area under the receiver operating characteristic curve.'],
  ['Brier score', 'brier_score', 'Mean squared error of predicted probabilities; lower is better.'],
  ['Brier Skill Score', 'brier_skill_score', 'Improvement in Brier score relative to training-only climatology.'],
  ['ECE', 'expected_calibration_error', 'Expected calibration error over the evaluation bins; lower is better.'],
  ['Top-20%-risk recall', 'top_20_percent_risk_recall', 'Share of observed busts captured by the highest-risk fifth of predictions.'],
] as const;

export function ModelInfoPanel({ model }: { model: ModelMetadata }) {
  const metrics = model.held_out_metrics.model;
  return (
    <aside className="model-panel" aria-label="Model information">
      <Accordion align="start">
        <AccordionItem title="Model and held-out evaluation">
          <dl className="model-facts">
            <div><dt>Model</dt><dd>{model.model_version}</dd></div>
            <div><dt>Feature contract</dt><dd>{model.feature_contract}</dd></div>
            <div><dt>Dataset</dt><dd>{model.dataset_version}</dd></div>
            <div><dt>Fit</dt><dd>{model.training_years.join('–')}</dd></div>
            <div><dt>Validate / calibrate</dt><dd>{model.validation_year}</dd></div>
            <div><dt>Held-out test</dt><dd>{model.test_year}</dd></div>
          </dl>
          <div className="metric-strip">
            {METRICS.map(([label, key, description]) => {
              const value = metrics[key];
              return (
                <div key={key}>
                  <DefinitionTooltip definition={description} align="bottom"><span>{label}</span></DefinitionTooltip>
                  <strong>{typeof value === 'number' ? value.toFixed(4) : '—'}</strong>
                </div>
              );
            })}
          </div>
          <p className="helper-text">Metrics are loaded from the versioned 2022 evaluation artifact. PR-AUC is the primary discrimination metric.</p>
        </AccordionItem>
      </Accordion>
    </aside>
  );
}
