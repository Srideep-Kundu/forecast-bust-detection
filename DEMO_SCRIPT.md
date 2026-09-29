# 3–4 Minute Judge Demo Script

## 0:00–0:20 — Problem

“Medium-range forecasts can occasionally develop very large errors, especially in rapidly changing situations. Our question is not ‘what weather will happen?’ but ‘where and at which lead time should a forecaster treat the numerical forecast with extra caution?’”

## 0:20–0:50 — Solution

“We produce a calibrated forecast-bust probability for each of 36 IMD subdivisions from Day 1 to Day 10. Forecast Reliability is exactly one minus that probability. The product then shows why the model moved the risk and which training-period forecasts looked most similar.”

## 0:50–1:20 — Architecture

“WeatherBench 2 forecasts and aligned HRES verification are processed offline. The classifier uses forecast-time-safe regional features. XGBoost produces the scientific score, a sigmoid calibrator converts it to probability, and deterministic SHAP plus historical analogs provide evidence. The Copilot comes only after this pipeline and cannot change any scientific value.”

## 1:20–2:50 — Live dashboard

1. Start on run `run-20220930T120000Z`.
2. Choose **Day 1 (+24h)**.
3. Point out the India risk map and explain that color and text represent calibrated probability, not hazard category.
4. Select **Lakshadweep (`imd-01`)** using the map or keyboard selector.
5. Read the exact Bust Probability and Forecast Reliability from the selected-region summary.
6. Show the **Day 1–10 lead-risk curve** and its accessible value table.
7. Switch to **Day 2**, note that the valid time and prediction ID update, then return to Day 1 if helpful.

Suggested wording: “These are historical replay results from saved, hash-validated 2022 predictions. The dashboard is not inventing or recomputing the probability in the browser.”

## 2:50–3:20 — Explainability and analogs

“The red and green SHAP lists show features that increased or decreased this model prediction relative to its baseline. We do not call these physical causes. Below them, the three analogs come only from 2018–2020 and are comparisons, not forecasts of the current case.”

## 3:20–3:50 — GenAI Copilot

1. Click **Why is this forecast risky?**.
2. Keep **Simple** mode and click **Ask Copilot**.
3. Point to the grounding tags beside the answer.

“Gemini is optional. If it is unavailable, this same endpoint returns a deterministic summary and the map, curve, SHAP, and analogs continue working.”

## 3:50–4:10 — Metrics and close

“On untouched 2022 data, PR-AUC is 0.754087, Brier score is 0.076600, and Brier Skill Score over regional lead-day climatology is 0.448570. The main contribution is an auditable reliability layer for deciding where forecast guidance deserves closer expert review.”

If the session must stay below four minutes, omit the Day 2 switch and quote only PR-AUC and BSS.
