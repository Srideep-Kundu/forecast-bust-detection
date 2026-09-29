# SIH Submission Summary — Forecast Bust Detection

## Problem

Medium-range weather forecasts sometimes develop unusually large errors during rapidly evolving systems. A single forecast value does not tell an operational forecaster where or when the forecast is most likely to be unreliable, making early review and resource prioritization difficult.

## Solution

This project estimates a calibrated forecast-bust probability for every Day 1–10 lead across the intended 36 IMD meteorological subdivisions. The dashboard presents that probability, its complementary Forecast Reliability, the model features that shifted the risk, and comparable training-period forecast states.

## Dataset

- Forecasts: official WeatherBench 2 IFS ENS mean product at 1.5° resolution.
- Verification: IFS HRES lead-zero analysis aligned to the forecast grid.
- Domain: India, 6–38°N and 68–98°E; June–September 2018–2022.
- Regions: validated 36-region IMD subdivision geometry with geodesic area weights.
- Complete labeled corpus: 439,200 region/lead rows.

Raw WeatherBench arrays stay in a local ignored cache. Derived redistribution is disabled until all applicable licenses are confirmed.

## Model

The comparison ladder is training-only climatology, deterministic logistic regression, and XGBoost. XGBoost is fitted on 2018–2020, its configuration is selected with 2021 validation results, and a sigmoid calibrator is fitted to isolated 2021 predictions. The final 2022 set remains untouched until evaluation.

## Explainability

- Exact TreeSHAP contributions identify which saved model inputs increased or decreased a particular predicted risk. They describe model behavior, not physical causation.
- Three nearest historical analogs are retrieved only from 2018–2020 standardized training records, prioritizing the same region and lead day.

## Dashboard

The Carbon React interface contains a 36-region calibrated risk map, a Day 1–10 lead-risk curve, Forecast Reliability, deterministic SHAP evidence, historical analogs, model metadata, loading/error states, and keyboard-accessible controls.

## GenAI Copilot

The optional Copilot is downstream of the scientific pipeline. It receives only a typed allowlist of already-computed evidence and cannot predict weather, alter probability or reliability, change SHAP, or replace analogs. When Gemini is disabled or unavailable, a deterministic evidence summary is returned and every P0 function remains available.

## Held-out 2022 metrics

| Metric | Value |
|---|---:|
| PR-AUC | 0.754087 |
| ROC-AUC | 0.916438 |
| Brier Score | 0.076600 |
| Brier Skill Score | 0.448570 |
| Expected Calibration Error | 0.025257 |
| Top-20%-risk Recall | 0.7269 |

## Reproducibility

- Dataset: `wb2-ifs-mean-india-v2`
- Feature contract: `mean-only-mvp-v2`
- Model: `xgb-bust-v2-mean-only`
- Prompt: `copilot-v1`

Manifests record sources, selection, row counts, units, versions, and hashes. Runtime refuses missing, incompatible, or hash-mismatched scientific artifacts.

## Limitations

- Historical replay only; the MVP has no live ingestion.
- P0 uses mean-only ensemble input and does not claim ensemble spread.
- This is a research decision-support prototype, not an official forecast or warning.
- Raw redistribution is prohibited; derived redistribution and geometry reuse remain source-license constrained.

## Future work

- Add true ensemble spread after provisioning suitable data-transfer and compute infrastructure.
- Add a validated live forecast adapter.
- Evaluate broader regional deployments with locally verified geometry and calibration.
