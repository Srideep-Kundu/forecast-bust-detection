import { lazy, Suspense, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { InlineNotification } from '@carbon/react';
import { api } from './api/client';
import { ControlBar } from './components/ControlBar';
import { DashboardHeader } from './components/DashboardHeader';
import { ModelInfoPanel } from './components/ModelInfoPanel';
import { PanelState } from './components/PanelState';
import { RegionSummary } from './components/RegionSummary';

const ExplanationPanel = lazy(() => import('./components/ExplanationPanel').then((module) => ({ default: module.ExplanationPanel })));
const LeadRiskCurve = lazy(() => import('./components/LeadRiskCurve').then((module) => ({ default: module.LeadRiskCurve })));
const RiskMap = lazy(() => import('./components/RiskMap').then((module) => ({ default: module.RiskMap })));

const IMMUTABLE_QUERY = { staleTime: Infinity, gcTime: 30 * 60 * 1000, retry: 1 } as const;

export default function App() {
  const [runId, setRunId] = useState('');
  const [leadDay, setLeadDay] = useState(1);
  const [regionId, setRegionId] = useState('');

  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000, retry: 1 });
  const model = useQuery({ queryKey: ['model'], queryFn: api.model, ...IMMUTABLE_QUERY });
  const runs = useQuery({ queryKey: ['runs'], queryFn: api.runs, ...IMMUTABLE_QUERY });
  const regions = useQuery({ queryKey: ['regions'], queryFn: api.regions, ...IMMUTABLE_QUERY });
  const geometry = useQuery({ queryKey: ['geometry'], queryFn: api.geometry, ...IMMUTABLE_QUERY });

  const selectedRunId = runId || runs.data?.[0]?.run_id || '';

  const riskMap = useQuery({
    queryKey: ['risk-map', selectedRunId, leadDay],
    queryFn: () => api.riskMap(selectedRunId, leadDay),
    enabled: Boolean(selectedRunId),
    ...IMMUTABLE_QUERY,
  });

  const selectedRegionId = riskMap.data?.risks.some((risk) => risk.region_id === regionId)
    ? regionId
    : riskMap.data?.risks[0]?.region_id ?? '';

  const selectedRisk = useMemo(
    () => riskMap.data?.risks.find((risk) => risk.region_id === selectedRegionId),
    [selectedRegionId, riskMap.data],
  );
  const leadCurve = useQuery({
    queryKey: ['lead-curve', selectedRunId, selectedRegionId],
    queryFn: () => api.leadCurve(selectedRunId, selectedRegionId),
    enabled: Boolean(selectedRunId && selectedRegionId),
    ...IMMUTABLE_QUERY,
  });
  const explanation = useQuery({
    queryKey: ['explanation', selectedRisk?.prediction_id],
    queryFn: () => api.explanation(selectedRisk!.prediction_id),
    enabled: Boolean(selectedRisk?.prediction_id),
    ...IMMUTABLE_QUERY,
  });

  const noRuns = !runs.isLoading && runs.data?.length === 0;

  return (
    <>
      <DashboardHeader health={health.data} isError={health.isError} />
      <main id="main-content" className="dashboard-shell">
        <ControlBar
          runs={runs.data}
          runId={selectedRunId}
          leadDay={leadDay}
          onRunChange={(value) => { setRunId(value); setRegionId(''); }}
          onLeadChange={setLeadDay}
          loading={runs.isLoading}
        />
        {health.isError ? <InlineNotification kind="error" lowContrast hideCloseButton title="Backend API unavailable" subtitle="Start the read-only API, then retry. Existing panel errors remain isolated below." /> : null}
        {runs.isError ? <PanelState kind="error" title="Forecast runs unavailable" message="The run catalog could not be loaded." /> : null}
        {noRuns ? <PanelState kind="empty" title="No replay runs" message="No versioned historical replay runs are available." /> : null}

        {selectedRunId ? (
          <>
            <RegionSummary risk={selectedRisk} />
            <div className="dashboard-grid">
              <div className="dashboard-grid__map">
                {riskMap.isLoading || geometry.isLoading ? <PanelState kind="loading" title="Loading risk map" tall /> : null}
                {riskMap.isError ? <PanelState kind="error" title="Risk map unavailable" message="The selected run and lead could not be loaded. Other panels remain available." tall /> : null}
                {geometry.isError ? <PanelState kind="error" title="Subdivision geometry unavailable" message="The validated region geometry could not be loaded." tall /> : null}
                {riskMap.data && riskMap.data.risks.length === 0 ? <PanelState kind="empty" title="No risk data" message="Choose another forecast run or lead day." tall /> : null}
                {riskMap.data?.risks.length && geometry.data ? (
                  <Suspense fallback={<PanelState kind="loading" title="Loading map renderer" tall />}>
                    <RiskMap geometry={geometry.data} risks={riskMap.data.risks} selectedRegionId={selectedRegionId} onSelectRegion={setRegionId} />
                  </Suspense>
                ) : null}
              </div>
              <div className="dashboard-grid__curve">
                {leadCurve.isLoading ? <PanelState kind="loading" title="Loading lead-risk curve" tall /> : null}
                {leadCurve.isError ? <PanelState kind="error" title="Lead curve unavailable" message="This region's Day 1–10 sequence could not be loaded." tall /> : null}
                {leadCurve.data ? <Suspense fallback={<PanelState kind="loading" title="Loading chart renderer" tall />}><LeadRiskCurve curve={leadCurve.data} selectedLead={leadDay} onSelectLead={setLeadDay} /></Suspense> : null}
              </div>
            </div>
            <div className="evidence-grid">
              <div>
                {!selectedRegionId ? <PanelState kind="empty" title="Select a subdivision" message="Choose a region on the map to inspect model evidence." /> : null}
                {explanation.isLoading ? <PanelState kind="loading" title="Loading deterministic explanation" tall /> : null}
                {explanation.isError ? <PanelState kind="error" title="Explanation unavailable" message="The map and lead curve are still usable." /> : null}
                {explanation.data ? <Suspense fallback={<PanelState kind="loading" title="Loading evidence renderer" tall />}><ExplanationPanel explanation={explanation.data} /></Suspense> : null}
              </div>
              <div>{model.isLoading ? <PanelState kind="loading" title="Loading model metadata" /> : null}{model.isError ? <PanelState kind="error" title="Model metadata unavailable" /> : null}{model.data ? <ModelInfoPanel model={model.data} /> : null}</div>
            </div>
          </>
        ) : null}
        <footer className="dashboard-footer">
          <p>Research decision-support prototype · Historical replay only · Not an official forecast or warning.</p>
          <p>{regions.data?.length === 36 ? 'Canonical 36-region manifest loaded' : 'Region manifest pending'}</p>
        </footer>
      </main>
    </>
  );
}
