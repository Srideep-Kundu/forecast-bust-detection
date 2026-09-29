import { useState } from 'react';
import { Button, InlineNotification, Select, SelectItem, SkeletonText, Tag, TextArea } from '@carbon/react';
import { api, ApiError } from '../api/client';
import type { CopilotResponse, PredictionExplanation } from '../api/types';

const QUICK_PROMPTS = [
  'Why is this forecast risky?',
  'Which factor matters most?',
  'What reduced the predicted risk?',
  'How is this similar to past cases?',
] as const;

const GROUNDING_LABELS: Record<string, string> = {
  bust_probability: 'Bust Probability',
  forecast_reliability: 'Forecast Reliability',
  top_positive_shap_drivers: 'Risk-increasing SHAP Drivers',
  top_negative_shap_drivers: 'Risk-decreasing SHAP Drivers',
  historical_analog_summaries: 'Historical Analogs',
  run_to_run_drift: 'Run-to-run Drift',
};

export function CopilotPanel({ explanation }: { explanation: PredictionExplanation }) {
  const [question, setQuestion] = useState('');
  const [mode, setMode] = useState<'simple' | 'meteorological'>('simple');
  const [answer, setAnswer] = useState<CopilotResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function askCopilot() {
    const normalized = question.trim();
    if (!normalized || loading) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const response = await api.copilot({
        prediction_id: explanation.prediction_id,
        question: normalized,
        explanation_mode: mode,
      });
      // A response for another prediction is never safe to display in this panel.
      if (response.prediction_id !== explanation.prediction_id) throw new Error('Prediction context mismatch');
      setAnswer(response);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'The explanation service could not be reached.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="copilot-panel" aria-labelledby="copilot-title">
      <div className="panel-heading">
        <div><span className="eyebrow">P1 · downstream explanation layer</span><h2 id="copilot-title">AI Copilot</h2></div>
        <Tag type="outline">Optional</Tag>
      </div>
      <p className="copilot-disclaimer">AI-generated explanation based only on the deterministic forecast-bust evidence shown in this dashboard. It does not independently predict weather or replace meteorological analysis.</p>
      <div className="copilot-controls">
        <TextArea
          id="copilot-question"
          labelText="Question about this prediction"
          maxLength={500}
          rows={3}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about risk drivers or historical analogs"
        />
        <Select id="copilot-mode" labelText="Explanation mode" value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
          <SelectItem value="simple" text="Simple" />
          <SelectItem value="meteorological" text="Meteorological" />
        </Select>
        <Button onClick={askCopilot} disabled={!question.trim() || loading}>{loading ? 'Generating…' : 'Ask Copilot'}</Button>
      </div>
      <div className="quick-prompts" aria-label="Suggested Copilot questions">
        {QUICK_PROMPTS.map((prompt) => <Button key={prompt} kind="ghost" size="sm" onClick={() => setQuestion(prompt)}>{prompt}</Button>)}
      </div>
      <div className="copilot-answer" aria-live="polite" aria-busy={loading}>
        {loading ? <><SkeletonText heading width="35%" /><SkeletonText paragraph lineCount={3} /></> : null}
        {error ? <InlineNotification kind="error" lowContrast hideCloseButton title="AI explanation unavailable" subtitle={`${error} Deterministic model evidence remains available above.`} /> : null}
        {answer?.degraded ? <InlineNotification kind="warning" lowContrast hideCloseButton title="AI explanation temporarily unavailable" subtitle="Deterministic model evidence is still available below. A deterministic evidence summary is shown." /> : null}
        {answer ? (
          <div className="copilot-response">
            <h3>{answer.degraded ? 'Deterministic evidence summary' : 'Grounded explanation'}</h3>
            <p>{answer.answer}</p>
            <div className="grounding-sources" aria-label="Evidence grounding sources">
              <strong>Grounded by</strong>
              <div>{answer.grounding_sources.map((source) => <Tag key={source} type="gray">{GROUNDING_LABELS[source] ?? source}</Tag>)}</div>
            </div>
            <small>{answer.llm_provider} · {answer.llm_model} · {answer.prompt_version}{answer.cached ? ' · cached' : ''}</small>
          </div>
        ) : null}
      </div>
    </section>
  );
}
