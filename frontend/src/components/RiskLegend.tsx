export function RiskLegend() {
  return (
    <div className="risk-legend" aria-label="Bust probability color scale from 0 to 100 percent">
      <span>Lower risk</span>
      <div className="risk-legend__scale" aria-hidden="true" />
      <span>Higher risk</span>
      <div className="risk-legend__ticks" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div>
      <p>Continuous calibrated probability—not model classes. Select a region for its exact value.</p>
    </div>
  );
}
