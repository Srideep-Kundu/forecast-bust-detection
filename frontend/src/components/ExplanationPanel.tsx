import type { PredictionExplanation } from '../api/types';
import { HistoricalAnalogs } from './HistoricalAnalogs';
import { ShapDrivers } from './ShapDrivers';
import { CopilotPanel } from './CopilotPanel';

export function ExplanationPanel({ explanation }: { explanation: PredictionExplanation }) {
  return (
    <section className="evidence-panel" aria-labelledby="evidence-title">
      <div className="panel-heading">
        <div><span className="eyebrow">Deterministic model evidence</span><h2 id="evidence-title">Why the model shifted this risk</h2></div>
        <code className="prediction-reference" title={explanation.prediction_id}>{explanation.prediction_id}</code>
      </div>
      <p className="helper-text">SHAP values describe how model features shifted this prediction relative to the model baseline. They do not establish physical causation.</p>
      <ShapDrivers positive={explanation.top_positive_drivers} negative={explanation.top_negative_drivers} />
      <HistoricalAnalogs analogs={explanation.historical_analogs} />
      <CopilotPanel key={explanation.prediction_id} explanation={explanation} />
    </section>
  );
}
