export function RiskLegend() {
  return (
    <div className="px-4 py-3 border-t border-[#1f2a1d]/10 bg-[#f8faf7] text-xs text-[#4b5b47] flex flex-col gap-2" aria-label="Bust probability color scale from 0 to 100 percent">
      <div className="flex items-center justify-between font-medium">
        <span className="text-[#336443]">Low Bust Risk (0%)</span>
        <span className="text-[#85AB8B]">Moderate (50%)</span>
        <span className="text-[#8c3b24]">Severe Bust Risk (100%)</span>
      </div>
      <div
        className="w-full h-2.5 rounded-full border border-[#1f2a1d]/15 shadow-inner"
        style={{
          background: 'linear-gradient(to right, #edf5eb 0%, #a3c9a8 25%, #e2b46c 50%, #d97043 75%, #78281f 100%)',
        }}
        aria-hidden="true"
      />
      <div className="flex justify-between items-center text-[11px] text-[#4b5b47]">
        <span>Continuous calibrated probabilistic prediction</span>
        <span className="font-mono">P(Bust | X)</span>
      </div>
    </div>
  );
}
