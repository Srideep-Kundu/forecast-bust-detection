# Forecast Bust Detection Product Requirements

## Document control

| Field | Value |
|---|---|
| Product | AI-Based Forecast Bust Detection for Medium-Range Weather Forecasts |
| Problem statement | SIH 26079, MoES / NCMRWF |
| MVP deadline | 29 September 2026 |
| Dataset version | `wb2-ifs-mean-india-v2` |
| Feature contract | `mean-only-mvp-v2` |
| Model version | `xgb-bust-v2-mean-only` |
| Status | P0 complete; P1 grounded Copilot, dashboard integration, and deployment-readiness configuration implemented |

Changes to dataset schema, feature semantics, units, entities, API contracts, or copilot grounding fields must be reflected in `prd.md`, `tech.md`, `flow.md`, `agents.md`, and `README.md` together.

## Product objective

Help operational forecasters identify Indian meteorological subdivisions and Day 1-10 lead times where a medium-range forecast is unusually likely to suffer a large multivariate error. The product presents a calibrated forecast-bust probability, a complementary Forecast Reliability value, deterministic evidence, and comparable historical cases.

This is a research decision-support prototype. It does not replace an official forecast, warning, or meteorologist.

## Users and decisions

- Operational forecaster: identifies low-reliability regions and inspects physical/model evidence before issuing guidance.
- Forecast verification analyst: studies error patterns by region and lead time.
- SIH evaluator: verifies scientific validity, traceability, explainability, and failure behavior.

The primary workflow is: choose a forecast run, choose a lead day, scan the map, inspect a region's Day 1-10 curve, review SHAP drivers and historical analogs, and optionally ask the GenAI Copilot to translate that evidence.

## Scope and priority

### P0: required scientific product

- Reproducible WeatherBench 2 dataset extraction and regional aggregation.
- XGBoost bust-risk model with probability calibration.
- Climatology and deterministic logistic-regression baselines.
- India subdivision risk map and Day 1-10 lead curve.
- Deterministic SHAP drivers and three training-only historical analogs.
- Read-only historical-replay API backed by verified Parquet/model artifacts; no runtime training or synthetic fallback.
- Provenance, model version, dataset version, and artifact hashes.
- Loading, empty, stale, partial-data, and error states.

### P1: implemented optional GenAI Copilot

- Translate already-computed structured evidence into plain language.
- Answer questions about existing model output in simple or meteorological terminology.
- Remain removable and disabled without affecting P0.

If time is constrained, all P0 acceptance criteria take precedence over P1.

### Out of scope

Authentication, PostgreSQL, Redis, Celery, Kafka, vector databases, live retraining, user feedback, live NOAA ingestion, LLM-generated predictions, and operational warnings.

## Dataset product requirements

- Forecast source: the official WeatherBench 2 IFS ENS precomputed mean product, 2018-2022, 1.5-degree grid. The production MVP performs no raw-member reads.
- The P0 feature contract contains deterministic mean fields and initialization-time-safe change/structure proxies only. Run-to-run drift, lead time, MSLP gradient, vorticity, and precipitation magnitude must not be called ensemble spread.
- P0 forecast columns are 2 m temperature; mean sea-level pressure; 10 m u/v and wind speed; 850 hPa wind and relative vorticity; 500-850 hPa thickness; 24-hour precipitation; MSLP gradient; run-to-run MSLP drift; lead day; seasonal sine/cosine; and categorical region ID.
- True 50-member MSLP, 10 m wind, temperature, and precipitation spreads are a post-MVP research enhancement. They are deferred because measured source-layout projections are approximately 1.151 TB for the former full-spread design and 350.43 GB for precipitation-only, versus 74.45 GB for the mean-only product; this is an infrastructure constraint, not a claim that spread is scientifically unnecessary.
- Verification source: IFS HRES lead-zero analysis aligned to the ENS grid before regional aggregation.
- Domain: 6-38 degrees north and 68-98 degrees east; June-September only.
- Leads: exactly 24, 48, 72, 96, 120, 144, 168, 192, 216, and 240 hours. Day 1 means +24 hours; Day 10 means +240 hours.
- Regions: the intended 36 IMD meteorological subdivisions. Setup must verify count, IDs, names, CRS, validity, topology, and intended-set correspondence rather than trusting the geometry source.
- Geometry repair must be explicit and reported. The validated source requires `make_valid` for region IDs 34 and 36; reported boundary slivers up to 5 km2 are tolerated, while larger overlaps fail validation.
- Raw WeatherBench/TIGGE arrays stay out of version control and must not be redistributed.
- Derived-data redistribution is disabled by default. It may be enabled only after all WeatherBench, ECMWF/TIGGE, and geometry licenses are confirmed to permit it.
- Dataset provenance must cite the [WeatherBench 2 data guide](https://weatherbench2.readthedocs.io/en/latest/data-guide.html) and the geometry source, [Indian_met_zones](https://github.com/India-Meteorological-Department/Indian_met_zones).
- WeatherBench's derived `total_precipitation_24hr` field does not carry a copied unit attribute. Its unit must be explicitly inherited as metres only after validating the underlying `total_precipitation` field and recording that resolution in provenance.

## Prediction semantics

The authoritative output is `bust_probability`, produced by the calibrated XGBoost pipeline. Define:

```text
forecast_confidence = 1.0 - bust_probability
```

The UI labels this value **Forecast Reliability** and displays:

> Forecast Reliability = 1 - predicted probability of a forecast bust.

A bust label is a research target based on a train-only multivariate severity threshold. It is not an assertion that every weather variable failed or that a particular hazardous event will occur.

## Functional requirements

### Risk overview

- Select an available forecast initialization and one Day 1-10 lead.
- Render each validated IMD subdivision using its calibrated bust probability.
- Show valid time, initialization time, data/model version, legend, and stale-data status.
- Selecting a region opens its details without losing run and lead selections.
- The implemented single-screen historical-replay dashboard uses the latest available run by default, keeps run/lead/region selection in local UI state, and renders only values returned by the read-only API.

### Region detail

- Show Day 1-10 bust probability and Forecast Reliability.
- Show deterministic top SHAP drivers with values and contribution direction.
- Show the three nearest eligible historical analogs, including date, distance, lead, and observed bust outcome.
- Show run-to-run drift and other deterministic change/structure evidence. Ensemble spread is unavailable in the P0 MVP and must not be implied.
- Never imply causality from SHAP or promise a weather outcome.

### GenAI Copilot

The copilot may answer:

- Why is this subdivision showing high forecast-bust risk?
- Which variables contributed most?
- How does Day 7 compare with Day 3?
- Which historical events are most similar?
- Summarize this region's forecast reliability.
- What changed from the previous run?
- Explain this in simple language or meteorological terminology.

It receives only the typed backend `CopilotContext` allowlist: prediction/run/region identity, region name, lead and source/valid times, bust probability, Forecast Reliability, model/dataset versions, positive and negative SHAP drivers, approved forecast feature values, historical-analog summaries, optional run-to-run drift, restricted provenance, and explanation mode. It never receives ensemble spread, current verification truth, raw arrays, full tables, filesystem paths, secrets, or arbitrary metadata. It must not perform prediction, calculate confidence, modify evidence, or fabricate a location, event, cause, value, date, or scientific conclusion. Unsupported questions receive: `The available model evidence does not support that conclusion.`

The implemented Gemini provider is backend-only and optional. The immutable prompt treats the question and every context string as untrusted data, prohibits tools and causality claims from SHAP, and distinguishes analogs from current forecasts. Explicit percentages/probabilities are checked against supplied probability and reliability, and a narrow post-generation guard rejects unsupported hazardous-event or causality claims; one stricter retry is allowed before deterministic fallback and an explicit insufficient-evidence statement. Only successful provider narratives enter the bounded, hashed SQLite cache, keyed by prediction, normalized question, mode, model, dataset, prompt, provider, and provider model.

Display beside the copilot:

> AI-generated explanation based only on the deterministic forecast-bust evidence shown in this dashboard. It does not independently predict weather or replace meteorological analysis.

If unavailable, display:

> AI explanation temporarily unavailable. Deterministic model evidence is still available below.

All P0 screens remain usable in that state, and the endpoint returns a deterministic probability/SHAP/analog summary. Changing run, region, lead day, or prediction ID clears the prior Copilot answer.

## UX and design requirements

Design read: operational public-sector analytics for meteorologists and SIH judges, with a sober, evidence-first visual language.

- Use IBM Carbon React as the sole component design system.
- Apply taste-skill at commit `c184364c58658b2f131b4ae8bd3d206cabb3deee` selectively because its landing-page patterns do not govern dense dashboards.
- Dials: `DESIGN_VARIANCE=3`, `MOTION_INTENSITY=2`, `VISUAL_DENSITY=8`.
- Use a neutral surface system, colorblind-safe semantic risk encoding, monospaced numerical values, consistent radii, visible focus states, and WCAG AA contrast.
- Motion is limited to meaningful state transitions and must honor reduced-motion settings.
- Do not use decorative gradients, glassmorphism, oversized marketing type, fake precision, or animation that competes with data.
- The implemented dashboard provides desktop and responsive single-column layouts, keyboard-operable controls, explicit panel-level loading/empty/error states, a text-and-color risk legend, and a tabular fallback for the Day 1-10 curve.

## Success criteria

- A judge can identify the highest-risk subdivision for any available run/lead and trace the value to a versioned prediction.
- Every map record exposes the required prediction contract and `0 <= bust_probability <= 1`.
- Forecast Reliability equals `1.0 - bust_probability` exactly.
- PR-AUC is the primary discrimination metric; the model is compared with both declared baselines.
- The declared baselines are training-only climatology and logistic regression over the allowed deterministic feature family, giving `climatology -> simple ML -> nonlinear ML`.
- Dataset, preprocessing, model, calibration, prediction, SHAP, and analog artifacts are reproducible and hashed.
- A stable replay prediction ID has the form `xgb-bust-v2-mean-only__YYYYMMDDTHHMMSSZ__imd-NN__dNN`; identical model/run/region/lead inputs produce the same ID.
- No feature or preprocessing artifact leaks validation/test information.
- Copilot removal or failure has no effect on P0.
- The five-year corpus is complete only when every expected 00/12 UTC June-September initialization has a verified 360-row atomic partition and the manifest reports no gaps. The labeled layer adds only training-fitted standardized errors, severity, threshold, and bust target; these fields are excluded from classifier inputs.
- Source acquisition and derived construction are separate restartable operations. Every India-only native-chunk cache artifact carries source coordinates, units, dimensions, and a checksum; corrupted or incomplete cache entries are rejected.

## Four-day delivery

1. **Data proof:** verify remote arrays, grids, variables, units, subdivision geometry, area weights, lead selection, and a small end-to-end derived partition.
2. **Scientific pipeline:** resume the complete year/month corpus, fit and persist training-only labels, temporal splits, baselines, XGBoost selection, calibration, metrics, SHAP, and analogs.
3. **Product integration:** implement FastAPI contracts, risk map, lead curve, evidence panels, and failure states.
4. **Verification and P1:** complete end-to-end tests and demo fixtures; add the copilot only after P0 passes.

## Risks and mitigations

- Source mismatch: schema and unit assertions fail before transformation.
- Grid mismatch: deterministic alignment/regridding is persisted and hashed; inconsistent alignment fails.
- Incorrect region source: compare against the expected 36-region manifest and fail on discrepancy.
- Leakage: timestamp assertions and year-isolated fit artifacts are mandatory.
- Rare positives: report PR-AUC, calibration, regional/lead slices, and baselines rather than accuracy alone.
- Licensing uncertainty: raw and derived redistribution remain disabled.
- LLM hallucination or outage: strict grounding, output validation, graceful fallback, and P0 independence.
