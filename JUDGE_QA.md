# Judge Q&A Bank

## What exactly is a forecast bust?

In this prototype, a bust is a reproducible binary research label derived from a weighted combination of regional absolute precipitation, MSLP, vector-wind, and temperature errors. Each error is robustly standardized using 2018–2020 data, and a row is positive when severity exceeds the training-only regional lead-day 85th percentile. It does not mean every variable failed or that a hazard occurred.

## Why XGBoost?

The input is structured regional tabular data with nonlinear interactions across lead, circulation, moisture, and seasonal features. XGBoost handles that form efficiently and supports exact TreeSHAP contributions. It also provided a clear nonlinear comparison above climatology and logistic regression.

## Why not deep learning?

The MVP operates on aggregated regional features rather than full global fields, so a tabular model is appropriate and easier to audit within four days. Deep learning would add compute and validation complexity without being automatically better for this contract. It remains a research option after a stronger benchmark and larger data design.

## Why mean-only ensemble input?

WeatherBench’s native full-member layout would require transferring much larger global chunks even for an India slice. Measured projections were unsuitable for the prototype, so P0 uses the official IFS ENS mean and never pretends deterministic proxies are ensemble spread. True spread is a documented future enhancement.

## Why WeatherBench?

WeatherBench 2 supplies consistently organized research-grade forecast and verification products across multiple years. It supports reproducible retrospective evaluation and precise source/version provenance. This project still validates every required variable, unit, grid, time, and lead rather than trusting the source implicitly.

## How do you avoid leakage?

All forecast features have source times at or before initialization, while verification appears only in target creation. Robust statistics, labels, thresholds, encoders, preprocessing, baselines, the classifier, and analog index use 2018–2020 only. Calibration uses 2021 predictions, and 2022 is evaluated once as a held-out set.

## How is probability calibrated?

After selecting the XGBoost configuration, the classifier is refitted on 2018–2020 only. Its 2021 scores and labels fit a separate sigmoid calibrator. The classifier never trains on 2021 before calibration.

## What does Brier Skill Score mean?

BSS is `1 - Brier_model / Brier_climatology`. A positive value means the probabilistic model improves on the training-only regional lead-day climatology baseline; the held-out value is 0.448570. It evaluates probability quality rather than only ranking.

## Why SHAP?

Exact TreeSHAP decomposes a saved XGBoost margin into feature contributions for one prediction. The implementation checks that base value plus contributions reconstructs the raw model margin. SHAP describes model contribution, not physical causation.

## Why historical analogs?

Analogs give forecasters concrete training-period comparisons in the same standardized feature space. Retrieval uses 2018–2020 only, prioritizes the same region and lead day, and never uses the query, validation, or test record as a candidate. They supplement, rather than determine, the probability.

## Does the LLM predict weather?

No. XGBoost is the authoritative bust-risk model, and the LLM sits after probability, SHAP, and analog retrieval. It can only translate an approved structured context into narrative.

## How do you prevent hallucination?

The backend sends a typed hard allowlist, treats every question and metadata string as untrusted data, and uses an immutable grounding instruction. It checks emitted percentages/probabilities, rejects unsupported event or causality claims, retries once, and then uses a deterministic fallback. LLM output cannot overwrite any evidence field.

## Why is this useful for NCMRWF or MoES?

It adds a region-and-lead reliability layer to help prioritize expert review of medium-range guidance. The evidence panels make the score auditable instead of presenting only an alert. Operational adoption would still require evaluation on agency data and workflows.

## Is it live?

No. The implemented MVP is a historical replay over saved 2021–2022 predictions, with 2022 reserved for test evaluation. A live adapter is future work and would need the same variable, unit, grid, timestamp, and provenance validation.

## Can it scale nationally?

The current product already covers the intended 36 IMD subdivisions. The offline corpus pipeline is restartable and partitioned, while runtime uses read-only DuckDB views. Operational scale would require managed artifact delivery, monitoring, and agency validation rather than a change to the probability semantics.

## What are the current limitations?

The system is historical replay, mean-only, monsoon-season focused, and tied to its WeatherBench/HRES verification design. It is not an official warning system and does not independently predict hazards. Data and geometry redistribution also remain license constrained.

## What happens if Gemini fails?

The endpoint returns a structured degraded response with a deterministic probability/SHAP/analog summary. The risk map, lead curve, SHAP, analogs, health, and prediction endpoints remain available. P0 is fully functional with `LLM_ENABLED=false`.

## What is novel here?

The prototype combines leakage-safe regional bust labeling, calibrated lead-specific probabilities, exact model attribution, constrained training-only analog retrieval, and a strictly downstream grounded explanation layer. The emphasis is not merely classification, but traceable uncertainty communication with artifact-level reproducibility.

## How is this different from a normal forecast dashboard?

A normal dashboard primarily displays predicted weather variables. This dashboard displays the probability that the underlying medium-range forecast will incur unusually large multivariate error for a region and lead. It is a reliability and verification decision-support layer, not another weather map.
