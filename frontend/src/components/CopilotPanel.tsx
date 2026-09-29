import { useState, useEffect } from 'react';
import { Bot, HelpCircle, ShieldCheck } from 'lucide-react';
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

  useEffect(() => {
    setQuestion('');
    setAnswer(null);
    setError(null);
    setLoading(false);
  }, [explanation.prediction_id]);

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
      if (response.prediction_id !== explanation.prediction_id) throw new Error('Prediction context mismatch');
      setAnswer(response);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'The explanation service could not be reached.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mt-8 pt-6 border-t border-[#1f2a1d]/10" aria-labelledby="copilot-title">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex flex-col">
          <span className="text-[11px] font-mono uppercase tracking-wider text-[#85AB8B] flex items-center gap-1">
            <Bot className="w-3 h-3 text-[#336443]" />
            Downstream Synthesis Layer
          </span>
          <h3 id="copilot-title" className="text-base font-semibold text-[#1f2a1d]">
            AI Copilot
          </h3>
        </div>
        <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#eef4ed] text-[#336443] border border-[#336443]/20">
          Optional Grounded Layer
        </span>
      </div>

      <p className="text-xs text-[#4b5b47] mb-4">
        AI-generated explanation based only on the deterministic forecast-bust evidence shown in this dashboard. It does not independently predict weather or replace meteorological analysis.
      </p>

      <div className="flex flex-col gap-3 bg-[#f8faf7] p-4 rounded-xl border border-[#1f2a1d]/10">
        <div className="flex flex-col gap-2">
          <label htmlFor="copilot-question" className="text-xs font-medium text-[#1f2a1d]">
            Question about this prediction
          </label>
          <div className="flex flex-col sm:flex-row gap-3">
            <textarea
              id="copilot-question"
              aria-label="Question about this prediction"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={2}
              maxLength={500}
              placeholder="Ask about specific atmospheric drivers or historical analogs..."
              className="w-full bg-white text-xs text-[#1f2a1d] px-3.5 py-2 rounded-lg border border-[#1f2a1d]/15 focus:border-[#336443] focus:ring-1 focus:ring-[#336443] outline-none transition-all resize-none"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex items-center gap-2">
            <label htmlFor="copilot-mode" className="text-xs font-medium text-[#4b5b47]">
              Explanation mode
            </label>
            <select
              id="copilot-mode"
              aria-label="Explanation mode"
              value={mode}
              onChange={(event) => setMode(event.target.value as typeof mode)}
              className="bg-white text-xs text-[#1f2a1d] font-medium px-3 py-1.5 rounded-lg border border-[#1f2a1d]/15 focus:border-[#336443] outline-none cursor-pointer"
            >
              <option value="simple">Simple</option>
              <option value="meteorological">meteorological</option>
            </select>
          </div>

          <button
            onClick={askCopilot}
            disabled={!question.trim() || loading}
            className="bg-[#1f2a1d] hover:bg-[#2a3827] disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors shadow-sm"
          >
            {loading ? 'Generating…' : 'Ask Copilot'}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 pt-1" aria-label="Suggested Copilot questions">
          <span className="text-[11px] text-[#4b5b47] flex items-center gap-1 mr-1">
            <HelpCircle className="w-3 h-3" /> Suggested:
          </span>
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => setQuestion(prompt)}
              className="text-[11px] font-medium text-[#336443] bg-white hover:bg-[#eef4ed] border border-[#336443]/20 px-2.5 py-1 rounded-md transition-colors"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      <div className="copilot-answer mt-4" aria-live="polite" aria-busy={loading}>
        {loading && (
          <div className="p-4 bg-white rounded-lg border border-[#1f2a1d]/10 animate-pulse flex flex-col gap-2">
            <div className="h-4 bg-[#eef4ed] rounded w-1/3" />
            <div className="h-3 bg-[#eef4ed] rounded w-full" />
            <div className="h-3 bg-[#eef4ed] rounded w-5/6" />
          </div>
        )}

        {error && (
          <div className="p-3 bg-amber-50 text-[#8c3b24] text-xs rounded-lg border border-[#8c3b24]/20 flex flex-col gap-1">
            <strong>AI explanation unavailable</strong>
            <p>{error} Deterministic model evidence remains available above.</p>
          </div>
        )}

        {answer?.degraded && (
          <div className="p-3 mb-3 bg-amber-50 text-[#8c3b24] text-xs rounded-lg border border-[#8c3b24]/20 flex flex-col gap-1">
            <strong>AI explanation temporarily unavailable</strong>
            <p>Deterministic model evidence is still available below. A deterministic evidence summary is shown.</p>
          </div>
        )}

        {answer && (
          <div className="copilot-response bg-white rounded-xl border border-[#1f2a1d]/10 p-5 shadow-sm flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[#336443] flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4" />
                {answer.degraded ? 'Deterministic evidence summary' : 'Grounded explanation'}
              </h3>
              <span className="text-[10px] font-mono text-[#85AB8B]">
                {answer.llm_provider} · {answer.llm_model} · {answer.prompt_version}
                {answer.cached ? ' · cached' : ''}
              </span>
            </div>

            <p className="text-xs text-[#1f2a1d] leading-relaxed">
              {answer.answer}
            </p>

            <div className="grounding-sources pt-3 border-t border-[#1f2a1d]/10 flex flex-wrap items-center gap-2" aria-label="Evidence grounding sources">
              <strong className="text-[11px] text-[#4b5b47] font-medium">Grounded by</strong>
              <div className="flex flex-wrap gap-1.5">
                {answer.grounding_sources.map((source) => (
                  <span
                    key={source}
                    className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#eef4ed] text-[#336443] border border-[#336443]/20"
                  >
                    {GROUNDING_LABELS[source] ?? source}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
