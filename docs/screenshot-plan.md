# Reproducible Screenshot Plan

All screenshots must come from the running local application. Do not composite, alter values, or substitute mock data.

## Fixed replay selection

- Run: `run-20220930T120000Z`
- Region: `imd-01` — Lakshadweep
- Lead: Day 1 (+24 hours)
- Model: `xgb-bust-v2-mean-only`
- Dataset: `wb2-ifs-mean-india-v2`
- Browser viewport: 1440 × 900 for desktop captures; keep browser zoom at 100%.

## Capture sequence

1. **India risk map**
   - Load the fixed run and Day 1.
   - Frame the header, selected-run controls, region summary, full map, and risk legend.
   - Ensure “Historical Replay” and the source/valid time remain visible.

2. **Selected region and lead curve**
   - Select Lakshadweep using the keyboard region selector or map.
   - Frame exact Bust Probability, Forecast Reliability, and the complete Day 1–10 curve.

3. **SHAP explanation**
   - Keep the fixed selection.
   - Scroll to “Why the model shifted this risk.”
   - Include the non-causality helper text and both contribution lists.

4. **Historical analogs**
   - Frame all three analog cards, their initialization dates, lead, distance, and historical bust status.
   - Keep the “training-period comparisons only” text visible.

5. **GenAI Copilot**
   - Click “Why is this forecast risky?” and submit in Simple mode.
   - If Gemini is not configured, capture the truthful degraded state and deterministic summary; do not disguise it as provider output.
   - Include grounding tags and the permanent disclaimer.

6. **Model metadata and metrics**
   - Expand “Model and held-out evaluation.”
   - Capture model/dataset versions, temporal split, PR-AUC, Brier/BSS, and calibration metadata.

## File naming

```text
01-risk-map-day1.png
02-region-lead-curve.png
03-shap-drivers.png
04-historical-analogs.png
05-grounded-copilot.png
06-model-metrics.png
```

Store final images in `docs/screenshots/` only after checking that each value matches the dashboard and no keys, local paths, or personal browser data are visible.
