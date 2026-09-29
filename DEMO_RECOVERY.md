# Demo Recovery and Offline Fallback

The core historical-replay application is local and works with `LLM_ENABLED=false`. Internet access and Gemini are not required for the map, lead curve, probability, SHAP, analogs, metrics, or deterministic Copilot fallback.

## Before leaving for the demo

1. Keep the complete local `data/` directory on the presentation laptop; do not rely on a fresh clone for license-gated artifacts.
2. Run `python -m pip check` and `npm audit` while networking is available.
3. Confirm these required paths exist:

```powershell
Test-Path data/manifests/full-dataset-manifest.json
Test-Path data/manifests/labeled-dataset-manifest.json
Test-Path data/reports/model-evaluation.json
Test-Path data/reports/held-out-predictions.parquet
Test-Path data/artifacts/xgboost-classifier.joblib
Test-Path data/artifacts/sigmoid-calibrator.joblib
Test-Path data/artifacts/preprocessor.joblib
Test-Path data/artifacts/analog-scaler.joblib
Test-Path data/geometry/expected_regions.json
Test-Path data/geometry/imd_subdivisions.geojson
```

Every command should return `True`. API startup performs deeper schema and hash validation.

## Start the offline demo

Terminal 1:

```powershell
$env:LLM_ENABLED='false'
forecast-bust api
```

Terminal 2:

```powershell
Set-Location frontend
Copy-Item .env.example .env.local -ErrorAction SilentlyContinue
npm run dev
```

Open `http://127.0.0.1:5173` and select `run-20220930T120000Z`, `imd-01`, Day 1.

## Health check

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json
```

Expected fields include `status: "ok"`, `model_loaded: true`, model `xgb-bust-v2-mean-only`, and dataset `wb2-ifs-mean-india-v2`. Core health never depends on Gemini.

## If Gemini fails

- Leave `LLM_ENABLED=false` or restart the backend with that value.
- The Copilot returns a deterministic evidence summary with a visible unavailable warning.
- Continue the demo using probability, Forecast Reliability, SHAP, analogs, and grounding tags.
- Never enter or expose a provider key in the browser.

## Restart procedures

### Backend

Press `Ctrl+C` in Terminal 1, then rerun:

```powershell
$env:LLM_ENABLED='false'
forecast-bust api
```

If startup fails, read the exact missing/hash-mismatch error and restore the validated local artifact copy. Do not edit manifests or substitute files during the demo.

### Frontend

Press `Ctrl+C` in Terminal 2, then run:

```powershell
Set-Location frontend
npm run dev
```

If port 5173 is occupied, stop the old Vite process rather than changing production configuration during judging.

## Last-resort static explanation

If the browser cannot start, use `SUBMISSION_SUMMARY.md` and the previously captured real screenshots. Clearly state that these are historical replay results. Do not present a mock UI or fabricated response as live output.
