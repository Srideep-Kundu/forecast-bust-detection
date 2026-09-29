import { lazy, Suspense, useMemo, useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Play, Sparkles, Menu, X, ArrowRight, Layers, ExternalLink } from 'lucide-react';
import { api } from './api/client';
import { ControlBar } from './components/ControlBar';
import { DashboardHeader } from './components/DashboardHeader';
import { ModelInfoPanel } from './components/ModelInfoPanel';
import { PanelState } from './components/PanelState';
import { RegionSummary } from './components/RegionSummary';
import BoomerangVideoBg from './components/BoomerangVideoBg';

const ExplanationPanel = lazy(() =>
  import('./components/ExplanationPanel').then((module) => ({ default: module.ExplanationPanel }))
);
const LeadRiskCurve = lazy(() =>
  import('./components/LeadRiskCurve').then((module) => ({ default: module.LeadRiskCurve }))
);
const RiskMap = lazy(() =>
  import('./components/RiskMap').then((module) => ({ default: module.RiskMap }))
);

const BG_VIDEO =
  'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260511_131941_d136af49-e243-493a-be14-6ff3f24e09e6.mp4';

const IMMUTABLE_QUERY = { staleTime: Infinity, gcTime: 30 * 60 * 1000, retry: 1 } as const;

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);

  const [runId, setRunId] = useState('');
  const [leadDay, setLeadDay] = useState(1);
  const [regionId, setRegionId] = useState('');

  useEffect(() => {
    if (menuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [menuOpen]);

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

  const scrollToStudio = (elementId = 'main-content') => {
    document.getElementById(elementId)?.scrollIntoView({ behavior: 'smooth' });
    setMenuOpen(false);
  };

  const navLinks = [
    { href: '#main-content', label: 'Spatial Risk Map', onClick: () => scrollToStudio('main-content') },
    { href: '#lead-curve-section', label: 'Lead Horizon Curve', onClick: () => scrollToStudio('lead-curve-section') },
    { href: '#evidence-section', label: 'SHAP Drivers', onClick: () => scrollToStudio('evidence-section') },
    { href: '#governance', label: 'Model Governance', onClick: () => scrollToStudio('governance') },
  ];

  return (
    <div className="min-h-screen bg-[#f8faf7] text-[#1f2a1d] flex flex-col selection:bg-[#85AB8B]/30">
      {/* Top Header */}
      <DashboardHeader health={health.data} isError={health.isError} />

      {/* HERO SECTION WITH BOOMERANG VIDEO */}
      <section className="relative w-full min-h-[92vh] sm:min-h-[88vh] overflow-hidden flex flex-col justify-between border-b border-[#1f2a1d]/10">
        <BoomerangVideoBg src={BG_VIDEO} className="absolute inset-0 w-full h-full" />
        
        {/* Semi-transparent tonal scrim for maximum readability */}
        <div className="absolute inset-0 bg-white/20 backdrop-brightness-[0.98] pointer-events-none" />

        {/* Hero Top Nav */}
        <nav className="relative z-30 flex items-center justify-between px-4 sm:px-6 md:px-10 py-4 sm:py-6">
          <div className="flex items-center gap-2 text-[#1f2a1d]">
            <span className="text-lg sm:text-xl md:text-2xl font-bold tracking-tight">
              BustWatch<sup className="text-[10px] sm:text-xs font-medium">TM</sup>
            </span>
          </div>

          <div className="hidden lg:flex items-center gap-1 bg-white/85 backdrop-blur-md rounded-full pl-6 pr-1.5 py-1.5 shadow-sm border border-white/70">
            {navLinks.map((link, i) => (
              <a
                key={link.label}
                href={link.href}
                onClick={link.onClick}
                className={`text-sm px-3.5 py-1.5 rounded-full transition-colors ${
                  i === 0 ? 'font-semibold text-[#1f2a1d] bg-[#eef4ed]' : 'font-medium text-[#2d3a2a] hover:text-[#1f2a1d]'
                }`}
              >
                {link.label}
              </a>
            ))}
            <button
              onClick={() => scrollToStudio('main-content')}
              className="ml-2 bg-[#1f2a1d] hover:bg-[#2a3827] text-white text-sm font-medium px-5 py-2 rounded-full transition-colors flex items-center gap-1.5"
            >
              <span>Explore Map</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-3 sm:gap-6 text-[#1f2a1d]">
            <a
              href="#main-content"
              onClick={() => scrollToStudio('main-content')}
              className="hidden sm:flex items-center gap-1.5 text-sm font-semibold bg-white/80 backdrop-blur-sm px-3.5 py-1.5 rounded-full border border-white/60 hover:bg-white transition-all shadow-xs"
            >
              <Layers className="w-4 h-4 text-[#1b4329]" />
              <span>Diagnostics</span>
            </a>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="hidden sm:flex items-center gap-1.5 text-sm font-semibold bg-white/80 backdrop-blur-sm px-3.5 py-1.5 rounded-full border border-white/60 hover:bg-white transition-all shadow-xs"
            >
              <span>API Specs</span>
              <ExternalLink className="w-3.5 h-3.5 text-[#1b4329]" />
            </a>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="lg:hidden relative flex items-center justify-center w-10 h-10 rounded-full bg-white/85 backdrop-blur-md border border-white/70 text-[#1f2a1d] transition-all duration-300 hover:bg-white"
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={menuOpen}
            >
              <Menu
                className={`w-5 h-5 absolute transition-all duration-300 ${
                  menuOpen ? 'opacity-0 rotate-90 scale-50' : 'opacity-100 rotate-0 scale-100'
                }`}
              />
              <X
                className={`w-5 h-5 absolute transition-all duration-300 ${
                  menuOpen ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 -rotate-90 scale-50'
                }`}
              />
            </button>
          </div>
        </nav>

        {/* Mobile menu overlay */}
        <div
          className={`lg:hidden fixed inset-0 z-40 transition-opacity duration-300 ${
            menuOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
          }`}
          onClick={() => setMenuOpen(false)}
        >
          <div className="absolute inset-0 bg-[#1f2a1d]/40 backdrop-blur-sm" />
        </div>

        {/* Mobile menu drawer */}
        <div
          className={`lg:hidden fixed top-0 right-0 bottom-0 z-50 w-[85%] max-w-sm bg-white/95 backdrop-blur-xl shadow-2xl transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${
            menuOpen ? 'translate-x-0' : 'translate-x-full'
          }`}
        >
          <div className="flex flex-col h-full pt-24 px-8 pb-8 justify-between">
            <div className="flex flex-col gap-1">
              {navLinks.map((link, i) => (
                <a
                  key={link.label}
                  href={link.href}
                  onClick={link.onClick}
                  className={`text-2xl font-semibold text-[#1f2a1d] py-4 border-b border-[#1f2a1d]/10 transition-all duration-500 ${
                    menuOpen ? 'translate-x-0 opacity-100' : 'translate-x-8 opacity-0'
                  }`}
                  style={{ transitionDelay: menuOpen ? `${150 + i * 70}ms` : '0ms' }}
                >
                  {link.label}
                </a>
              ))}
            </div>

            <div
              className={`flex flex-col gap-4 transition-all duration-500 ${
                menuOpen ? 'translate-x-0 opacity-100' : 'translate-x-8 opacity-0'
              }`}
              style={{ transitionDelay: menuOpen ? '350ms' : '0ms' }}
            >
              <button
                onClick={() => scrollToStudio('main-content')}
                className="bg-[#1f2a1d] hover:bg-[#2a3827] text-white text-sm font-semibold px-5 py-3 rounded-full transition-colors flex items-center justify-center gap-2"
              >
                <span>Launch Diagnostics</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Hero copy */}
        <div className="relative z-10 flex flex-col items-center text-center pt-12 sm:pt-16 md:pt-20 px-4 sm:px-6">
          <h1
            className="font-bold leading-[0.95] text-[#143820] text-[2.15rem] sm:text-4xl md:text-5xl lg:text-[4.75rem] xl:text-[5.25rem] max-w-5xl drop-shadow-[0_1px_2px_rgba(255,255,255,0.7)]"
            style={{
              fontFamily:
                '"Neue Haas Grotesk Display Pro 55 Roman", "Neue Haas Grotesk Text Pro", "Helvetica Neue", Helvetica, Arial, sans-serif',
              letterSpacing: '-0.035em',
            }}
          >
            Anticipate the shift{' '}
            <span className="text-[#1e613b]">
              detecting forecast busts
              <br className="hidden sm:block" /> before they unfold
            </span>
          </h1>

          {/* High-legibility frosted subtitle container */}
          <div className="mt-6 sm:mt-8 px-5 sm:px-6 py-2.5 rounded-2xl bg-white/85 backdrop-blur-md border border-white/70 shadow-sm max-w-xl">
            <p className="text-[#142213] text-sm sm:text-base font-medium leading-relaxed">
              Machine-learning decision support isolating numerical weather prediction failure risks across 36 Indian meteorological subdivisions.
            </p>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="relative z-10 w-full px-4 sm:px-6 md:px-10 pb-6 sm:pb-8 flex flex-col sm:flex-row items-start sm:items-end justify-between gap-6">
          {/* Bottom-left CTA block with clear frosted container */}
          <div className="max-w-md bg-white/85 backdrop-blur-md p-5 sm:p-6 rounded-2xl border border-white/70 shadow-sm">
            <div className="flex items-center gap-2 text-[#143820] mb-2 font-semibold">
              <Sparkles className="w-4 h-4 text-[#1e613b]" />
              <span className="text-sm font-semibold">
                AeroRisk Engine<sup className="text-[10px]">TM</sup>
              </span>
            </div>
            <p className="text-[#142213] text-xs leading-relaxed mb-4 max-w-sm font-medium">
              BustWatch continuously diagnoses numerical weather prediction outputs, pinpointing atmospheric anomaly patterns and dynamical bust risks up to 10 days in advance.
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <button
                onClick={() => scrollToStudio('main-content')}
                className="bg-[#1f2a1d] hover:bg-[#2a3827] text-white text-xs font-semibold px-5 py-2.5 rounded-full transition-colors shadow-sm flex items-center gap-1.5"
              >
                <span>Explore 36 Subdivisions</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => scrollToStudio('governance')}
                className="text-[#143820] hover:text-[#1e613b] text-xs font-semibold px-3 py-2 transition-colors underline decoration-[#1e613b]/40 underline-offset-4"
              >
                Model Governance
              </button>
            </div>
          </div>

          {/* Bottom-right video link */}
          <div className="hidden sm:flex items-center gap-2 text-[#143820] bg-white/85 backdrop-blur-md px-4 py-2 rounded-full border border-white/70 text-xs shadow-sm font-medium">
            <button
              onClick={() => scrollToStudio('main-content')}
              className="flex items-center justify-center w-6 h-6 rounded-full bg-[#1f2a1d] text-white hover:bg-[#2a3827] transition-colors"
              aria-label="Play video"
            >
              <Play className="w-2.5 h-2.5 fill-white text-white ml-0.5" />
            </button>
            <span className="font-semibold">Day 1–10 Verification</span>
            <span className="text-[#2d3a2a] font-mono">1:35</span>
          </div>
        </div>
      </section>

      {/* DIAGNOSTIC STUDIO & DECISION SUPPORT SUITE */}
      <main id="main-content" className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 flex-1 flex flex-col">
        <ControlBar
          runs={runs.data}
          runId={selectedRunId}
          leadDay={leadDay}
          onRunChange={(value) => {
            setRunId(value);
            setRegionId('');
          }}
          onLeadChange={setLeadDay}
          loading={runs.isLoading}
        />

        {health.isError && (
          <div className="cds--inline-notification p-4 mb-6 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-900">
            <strong>Backend API unavailable:</strong> Start the read-only API, then retry. Existing panel errors remain isolated below.
          </div>
        )}

        {runs.isError && (
          <PanelState kind="error" title="Forecast runs unavailable" message="The run catalog could not be loaded." />
        )}

        {noRuns && (
          <PanelState kind="empty" title="No replay runs" message="No versioned historical replay runs are available." />
        )}

        {selectedRunId && (
          <div className="flex flex-col gap-6">
            <RegionSummary risk={selectedRisk} />

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div id="risk-map-section" className="lg:col-span-7">
                {riskMap.isLoading || geometry.isLoading ? (
                  <PanelState kind="loading" title="Loading risk map" tall />
                ) : null}
                {riskMap.isError ? (
                  <PanelState
                    kind="error"
                    title="Risk map unavailable"
                    message="The selected run and lead could not be loaded. Other panels remain available."
                    tall
                  />
                ) : null}
                {geometry.isError ? (
                  <PanelState
                    kind="error"
                    title="Subdivision geometry unavailable"
                    message="The validated region geometry could not be loaded."
                    tall
                  />
                ) : null}
                {riskMap.data && riskMap.data.risks.length === 0 ? (
                  <PanelState kind="empty" title="No risk data" message="Choose another forecast run or lead day." tall />
                ) : null}
                {riskMap.data?.risks.length && geometry.data ? (
                  <Suspense fallback={<PanelState kind="loading" title="Loading map renderer" tall />}>
                    <RiskMap
                      geometry={geometry.data}
                      risks={riskMap.data.risks}
                      selectedRegionId={selectedRegionId}
                      onSelectRegion={setRegionId}
                    />
                  </Suspense>
                ) : null}
              </div>

              <div id="lead-curve-section" className="lg:col-span-5">
                {leadCurve.isLoading ? (
                  <PanelState kind="loading" title="Loading lead-risk curve" tall />
                ) : null}
                {leadCurve.isError ? (
                  <PanelState
                    kind="error"
                    title="Lead curve unavailable"
                    message="This region's Day 1–10 sequence could not be loaded."
                    tall
                  />
                ) : null}
                {leadCurve.data ? (
                  <Suspense fallback={<PanelState kind="loading" title="Loading chart renderer" tall />}>
                    <LeadRiskCurve
                      curve={leadCurve.data}
                      selectedLead={leadDay}
                      onSelectLead={setLeadDay}
                    />
                  </Suspense>
                ) : null}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-6">
              <div id="evidence-section">
                {!selectedRegionId ? (
                  <PanelState
                    kind="empty"
                    title="Select a subdivision"
                    message="Choose a region on the map or selector above to inspect deterministic model evidence."
                  />
                ) : null}
                {explanation.isLoading ? (
                  <PanelState kind="loading" title="Loading deterministic explanation" tall />
                ) : null}
                {explanation.isError ? (
                  <PanelState
                    kind="error"
                    title="Explanation unavailable"
                    message="The map and lead curve are still usable."
                  />
                ) : null}
                {explanation.data ? (
                  <Suspense fallback={<PanelState kind="loading" title="Loading evidence renderer" tall />}>
                    <ExplanationPanel explanation={explanation.data} />
                  </Suspense>
                ) : null}
              </div>

              <div id="governance">
                {model.isLoading ? <PanelState kind="loading" title="Loading model metadata" /> : null}
                {model.isError ? <PanelState kind="error" title="Model metadata unavailable" /> : null}
                {model.data ? <ModelInfoPanel model={model.data} /> : null}
              </div>
            </div>
          </div>
        )}

        <footer className="mt-12 pt-6 border-t border-[#1f2a1d]/10 text-xs text-[#4b5b47] flex flex-col sm:flex-row items-center justify-between gap-4">
          <p>BustWatch Decision Support Prototype · Historical Replay · NCMRWF & IMD Verification Benchmarks.</p>
          <div className="flex items-center gap-4">
            <span className="font-mono">
              {regions.data?.length === 36 ? 'Canonical 36-region manifest loaded' : 'Region manifest pending'}
            </span>
            <a href="#terms" className="hover:underline">Research Terms</a>
            <a href="#privacy" className="hover:underline">Data Policy</a>
          </div>
        </footer>
      </main>
    </div>
  );
}
