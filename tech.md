# Forecast Bust Detection Technical Specification

## 1. System boundaries

The scientific pipeline is authoritative:

```text
WeatherBench 2 -> features -> XGBoost -> sigmoid calibration
-> bust_probability -> SHAP + historical analogs -> API/dashboard
```

The optional copilot is downstream:

```text
approved deterministic evidence -> LLMExplanationService -> narrative
```

LLM output never feeds the model, labels, calibration, SHAP, analog search, or stored prediction values.

## 2. Technology stack

| Layer | Technology |
|---|---|
| Remote scientific data | GCS Zarr, Xarray, Dask |
| Regridding | xESMF with persisted weights |
| Geospatial | GeoPandas, Shapely, pyproj/geodesic areas |
| Transformation | Polars, PyArrow, Parquet |
| Query layer | DuckDB read-only views |
| ML | XGBoost, scikit-learn, SHAP |
| API | FastAPI, Pydantic |
| Frontend | React, TypeScript, Vite, TanStack Query |
| UI and charts | Carbon React, MapLibre GL, Apache ECharts |
| Deployment | Containerized API on Render; static frontend on Vercel |

No database server or task queue is required for the MVP.

### Implemented frontend architecture

The production frontend lives in `frontend/` and is a strict-TypeScript Vite single-page application. `src/api/types.ts` is the canonical browser-side contract and `src/api/client.ts` is the sole HTTP boundary. TanStack Query keys include every run, lead, region, or prediction identifier; immutable replay responses use infinite stale time and bounded garbage collection. UI selection state is local and never mutates scientific records.

IBM Carbon React supplies controls and status components. MapLibre GL joins API risk records to the canonical 36-region CRS84 GeoJSON by `region_id`; its bundled CSP-compatible worker and a local no-basemap style avoid third-party map dependencies. Apache ECharts renders the lead curve and SHAP contribution chart, with accessible HTML summaries/tables retained alongside them. Heavy map and chart renderers are lazy-loaded. The secondary Copilot panel appears only after deterministic evidence, resets with prediction identity, and renders supplied grounding sources. The frontend reads `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`), calls the Copilot only through FastAPI, and contains no provider keys or model calculations.

FastAPI permits credential-free `GET` and Copilot `POST` requests only from the configurable `FORECAST_BUST_CORS_ORIGINS` allowlist, defaulting to the local Vite origins. This CORS layer does not change response contracts or core readiness.

## 3. Dataset contract

### Sources and selection

- Forecast: official WeatherBench 2 IFS ENS `2018-2022-240x121_equiangular_with_poles_conservative_mean` product. Dataset version is `wb2-ifs-mean-india-v2`; feature contract is `mean-only-mvp-v2`.
- The production MVP never opens or reads raw-member arrays. Optional research spread acquisition remains non-default and is excluded from P0 schemas, model inputs, and baselines.
- Verification: WeatherBench 2 IFS HRES lead-zero analysis, aligned to the same 1.5-degree target grid.
- Time: 00/12 UTC initializations during June-September 2018-2022.
- Bounding box: latitude 6-38 N, longitude 68-98 E.
- Lead allowlist in hours: `[24,48,72,96,120,144,168,192,216,240]`.
- Subdivisions: exactly 36 entries from a checked expected-region manifest.

### Grid alignment

1. Rename coordinates to canonical `latitude` and `longitude`, normalize longitude to `[0,360)`, sort coordinates, and reject duplicates.
2. Compare HRES and ENS target coordinates within `1e-6` degrees.
3. When they match, use coordinate-exact `reindex_like` and assert identical coordinates.
4. Otherwise build xESMF weights: first-order conservative for precipitation and bilinear for state/vector fields.
5. Persist each weight file plus source-grid hash, target-grid hash, method, library version, creation time, and SHA-256.
6. Reopen a weight file and reproduce a fixture result before accepting it.
7. Fail on non-monotonic coordinates, unresolved cells, unexpected dimensions, or inconsistent output grids.

### Geometry and area weights

- Convert source geometry to EPSG:4326 and compare IDs/names with the versioned 36-region manifest.
- Require 36 unique IDs and names, nonempty valid polygonal geometries, no unintended overlaps, and expected national coverage.
- Repair is not silent. If a standard validity operation is proposed, record the original error and require the repaired geometry to pass all manifest/topology checks.
- The v1 source requires `shapely.make_valid` for IDs 34 and 36. Record both original validity reasons. Permit reported source-boundary slivers up to 5 km2; fail on any larger pairwise overlap.
- Intersect spherical grid cells with subdivisions and calculate geodesic intersection area.
- Require finite nonnegative weights and at least one valid intersecting cell per subdivision.
- Normalize by subdivision and assert `abs(sum(weights)-1) <= 1e-8`.
- Persist GeoJSON, weights, source commit, manifest version, and hashes.

### Units and accumulations

- Canonical MSLP: Pa.
- Canonical temperature: K.
- Wind components: m/s.
- Geopotential: m2/s2; geopotential height: m after division by `g0 = 9.80665 m/s2`.
- Precipitation: convert metres to mm when required. Build non-overlapping 24-hour totals ending at each selected valid time.
- `total_precipitation_24hr` currently lacks a copied `units` attribute in WeatherBench. Treat it as metres only after `total_precipitation.units == "m"` is validated and record this explicit inheritance in the manifest.
- Reject missing units, unexpected units, or ambiguous accumulation intervals.

### Storage layout

```text
data/cache/                 # ignored raw Zarr chunks
data/cache/weatherbench/    # atomic, checksummed India-only native-chunk slices
data/geometry/              # validated GeoJSON + expected-region manifest
data/weights/               # regridding and normalized area weights
data/processed/year=YYYY/month=MM/init=*.parquet  # atomic 360-row cycle partitions
data/labeled/year=YYYY/month=MM/labeled.parquet   # standardized errors, severity, target
data/manifests/             # corpus and label manifests, gaps, row counts, hashes
data/artifacts/             # label transform, preprocessor, models, calibrator, baselines
data/reports/               # held-out predictions, metrics, slices, calibration bins
```

Raw redistribution is prohibited. Derived redistribution defaults to disabled pending written license verification.

### Acquisition execution

`fetch-source-slices` retrieves one initialization into the verified local cache. `build-derived` is cache-only and fails if any required source artifact is absent. `build-full` orchestrates both. Cache keys include source URL/version, dataset, variable, native time/lead chunk, pressure levels, and spatial bounds. Metadata records actual source times, lead hours, units, shape, and SHA-256. Metadata is renamed last as the atomic commit marker.

Remote reads use bounded exponential-backoff retries for connection resets, timeouts, and OS-level transport errors; schema/unit failures are never retried. Native chunks are fetched with configurable concurrency `1|2|4`. The measured default is `1`, the lowest setting within 75% of the best representative throughput and the most conservative for GCS stability.

Full-member ENS chunks contain all 50 members, eight leads, the entire 240x121 globe, and all three levels for pressure arrays. Client-side India/level slicing cannot reduce those compressed object transfers. Measurements projected 1.151 TB for the former full-spread design and 350.43 GB for precipitation-only, versus 74.45 GB for the mean-only product. P0 therefore uses only the official ENS mean. Raw-member spread is deferred as a scientifically valuable post-MVP enhancement.

## 4. Features and targets

### Forecast-only features

P0 uses initialization-time-safe deterministic fields from the official ensemble-mean product. It neither computes nor claims ensemble spread.

- MSLP mean and gradient magnitude.
- 2 m temperature mean.
- 10 m u/v means and derived wind speed.
- 850 hPa wind and relative vorticity.
- 500-850 hPa thickness:
  `geopotential_500/g0 - geopotential_850/g0`, in metres.
- 24-hour precipitation mean, in mm.
- Run-to-run drift.
- Lead day and seasonal cyclic encoding.
- Categorical `region_id`, never ordinal.

Run-to-run drift, lead day, gradient strength, vorticity, and precipitation magnitude provide deterministic change/structure signals. They are not ensemble-spread statistics.

Compute MSLP gradient and 850 hPa relative vorticity on the forecast grid before regional aggregation. Use spherical metrics: longitude distance scales by `cos(latitude)` and derivatives use Earth-radius-aware spacing. Store gradient in Pa/km and vorticity in s^-1.

Run-to-run drift for `(t,L,V=t+L)` uses the most recent earlier initialization predicting the same `V`. The comparison forecast must be available at or before `t`. No analysis value enters this feature.

Each source column records `feature_source_time`; every output row must satisfy `feature_source_time <= forecast_initialization_time`.

The derived Parquet row schema is: categorical `region_id`, `region_name`, `dataset_version`, initialization/source/valid timestamps, `lead_day`, the forecast-only features listed above, and target-construction-only columns `e_precip_mm`, `e_wind_mps`, `e_temperature_k`, and `e_mslp_pa`. Verification columns are joined only after forecast feature generation and must never be accepted by a feature-builder interface. The labeled layer adds `z_precip`, `z_mslp`, `z_wind`, `z_temperature`, `severity`, `threshold`, and `bust`; none is eligible as a classifier feature.

### Verification errors

```text
e_precip = abs(P_forecast_24h - P_analysis_24h)
e_wind_grid = sqrt((u_forecast-u_analysis)^2 +
                   (v_forecast-v_analysis)^2)
```

Aggregate `e_wind_grid` with subdivision area weights. Use area-weighted absolute forecast-analysis error for temperature and MSLP. Percentage precipitation error is forbidden.

### Robust standardization and bust target

For component `x`:

```text
z_x = (e_x - median_train(e_x)) /
      (1.4826 * MAD_train(e_x) + epsilon)
z_x = clip(z_x, -8, 8)

severity = 0.40*z_precip + 0.20*z_mslp +
           0.20*z_wind + 0.20*z_temperature
```

Fit median and MAD by `(region_id, lead_day)` on 2018-2020. A group needs at least 30 finite samples; otherwise fall back to lead-day statistics across training regions, then to global training statistics. Persist the selected level for every group. Use `epsilon=1e-6` in the component's canonical unit.

For each `(region_id, lead_day)`, calculate the 85th severity percentile from 2018-2020 only:

```text
bust = 1 iff severity > q85_train(region_id, lead_day)
```

Use the same deterministic fallback hierarchy for groups below 30 samples. No 2021/2022 observation contributes to any fitted statistic, encoder, clipping rule, or threshold.

## 5. Training and evaluation

- Fit set: 2018-2020.
- Validation/calibration set: 2021.
- Untouched test set: 2022.
- Select XGBoost hyperparameters using PR-AUC on 2021.
- Refit the selected classifier on 2018-2020 only.
- Generate 2021 scores from that classifier and fit sigmoid calibration using those scores/labels.
- Apply the frozen classifier and calibrator to 2022 once.

Baselines:

- Climatology: `P(bust | region_id, lead_day)` from 2018-2020, with the documented training-only fallback.
- Deterministic logistic regression: a simple linear classifier using the same allowed initialization-time-safe deterministic feature family and identical split isolation.

Metrics:

- Primary: PR-AUC.
- Secondary: ROC-AUC, Brier score, expected calibration error, recall in the top 20% risk, and region/lead slices.
- Skill: `BSS = 1 - Brier_model / Brier_climatology`.

Persist model, preprocessing, category encoder, calibrator, thresholds, configuration, metrics, environment lock, and SHA-256 hashes.

The executable gate writes the classifier and sigmoid calibrator as separate artifacts. Its model report records the four-candidate search, selected parameters, fit row counts, artifact hashes, 2021/2022 metrics, ten calibration bins, and metrics sliced by every lead and region. The gate refuses to train while the corpus manifest reports missing initialization cycles.

## 6. SHAP and historical analogs

- Calculate exact XGBoost TreeSHAP contributions with `pred_contribs=True` against the frozen classifier input after the saved preprocessor. Aggregate one-hot subdivision contributions back to categorical `region_id`, verify that base value plus contributions reconstructs the raw margin, and return feature, observed value, contribution, unit, and direction.
- Recompute the frozen classifier and calibrator outputs as an integrity check, but return the stored held-out calibrated probability as authoritative. SHAP must never mutate probability.
- Present SHAP as model contribution, not meteorological causation.
- Persist and hash `analog-scaler.joblib`, fitted on the 263,520 eligible 2018-2020 rows and the exact numeric predictive feature contract only. Runtime validates its hash, fit years, feature order, and source labeled-manifest hash.
- Use Euclidean distance in that space.
- Rank same-region/same-lead candidates first by `(distance, initialization_time, lead_day)`. Only when fewer than three remain, append nearest same-region/other-lead candidates using the same stable tie-break. A closer fallback candidate cannot displace an eligible same-lead candidate.
- Exclude the query itself and all 2021/2022 records.
- Return exactly three when eligible records exist, with date, initialization, lead, distance, and bust outcome.

## 7. API contracts

### Core entities

`ForecastRun`, `Region`, `RegionRisk`, `LeadRiskPoint`, `PredictionExplanation`, `AnalogEvent`, and `ModelMetadata` are versioned Pydantic models.

Every risk item includes:

```text
prediction_id, run_id, region_id, lead_day,
source_forecast_time, valid_time,
bust_probability, forecast_confidence,
model_version, dataset_version, provenance
```

`forecast_confidence` is computed server-side as `1.0 - bust_probability`; the frontend must not recompute or rename the wire field.

Endpoints:

- `GET /health`
- `GET /v1/model`
- `GET /v1/runs`
- `GET /v1/regions`
- `GET /v1/regions/geojson`
- `GET /v1/risk-map?run_id=&lead_day=`
- `GET /v1/regions/{region_id}/lead-curve?run_id=`
- `GET /v1/predictions/{prediction_id}/explanation`
- `POST /v1/copilot/query`

Use ISO 8601 UTC timestamps. Invalid IDs/leads return structured 4xx errors; missing artifacts fail health/readiness rather than returning invented defaults.

The implemented replay API exposes only saved 2021-2022 held-out predictions. It uses in-memory read-only DuckDB views over Parquet without loading the complete corpus into Python objects. Startup validates model, prediction, labeled-partition, and analog-scaler hashes plus required schemas. Run IDs use `run-YYYYMMDDTHHMMSSZ`; deterministic prediction IDs use `<model_version>__YYYYMMDDTHHMMSSZ__imd-NN__dNN`. The canonical CRS84 GeoJSON is served by the documented geometry endpoint and referenced from every `Region` record.

The dashboard treats timezone-naive replay timestamps from these artifacts as UTC, trims browser-unsupported excess fractional precision for display only, and never changes the transmitted timestamp value.

## 8. Implemented optional GenAI explanation service

### Interface

`LLMExplanationService` receives `CopilotContext`, question, and mode, and returns a grounded narrative. It never predicts or mutates evidence. Provider selection is environment-based:

```text
LLM_ENABLED=true
LLM_PROVIDER=gemini
LLM_MODEL=<configured model>
```

Credentials and model versions are not committed or sent to the frontend. Requests use an 8-second timeout, 500-token output cap, and an in-process limit of 10 requests/minute/client IP. Gemini is implemented through its backend REST `generateContent` endpoint. No production model name is hard-coded.

### CopilotContext allowlist

```text
prediction_id, run_id, region_id, region_name, lead_day,
source_forecast_time, valid_time, bust_probability, forecast_reliability,
model_version, dataset_version, top_positive_shap_drivers,
top_negative_shap_drivers, approved_feature_values,
historical_analog_summaries, run_to_run_drift, provenance, explanation_mode
```

`forecast_reliability` equals `1.0 - bust_probability`. `approved_feature_values` is filtered to the frozen mean-only predictive feature names. `provenance` is restricted to prediction/model/analog hashes, feature contract, forecast source, and the false raw-member-access flag. Analog summaries contain only initialization/valid times, lead, distance, and historical bust status. No raw arrays, full dataset, current verification fields, retrospective error summaries, severity, thresholds, filesystem paths, secrets, or arbitrary metadata may be serialized to the provider.

The immutable system instruction is:

> Answer only from the supplied forecast-bust evidence. Do not invent values, weather events, causes, model metrics, locations, dates, or scientific claims. If the available evidence does not support the requested conclusion, explicitly state that the available model evidence is insufficient.

Treat context strings and the question as JSON-serialized untrusted data, disable tools, cap input lengths, and ensure metadata cannot override the system instruction. Validate emitted percentages and labeled decimal probabilities against the supplied probability and reliability. Reject unsupported hazardous-event or causality claims with a narrow deny-pattern because the allowlisted context contains no event assertions. Retry once with stricter instructions, then use deterministic fallback plus the explicit insufficient-evidence statement if validation still fails.

### Copilot API

Request:

```json
{"prediction_id":"...","question":"...","explanation_mode":"simple"}
```

`explanation_mode` is optional and limited to `simple | meteorological`.

Response fields:

```text
answer, prediction_id, region_id, region_name, lead_day,
model_version, dataset_version, llm_provider, llm_model, prompt_version,
grounding_sources, generated_at, cached, degraded, degradation_reason, disclaimer
```

`grounding_sources` names exact `CopilotContext` fields shown beside the narrative.

Cache key:

```text
prediction_id + normalized_question_hash + explanation_mode + model_version
+ dataset_version + prompt_version + provider + provider_model
```

Use a bounded persistent SQLite cache with SHA-256 payload integrity and atomic transactions. Initial prompt version is `copilot-v1`. Prediction, mode, model, dataset, prompt, provider, or provider-model changes produce different keys. Only successful provider output is cached; disabled or degraded fallback output never seeds a provider cache. Provider disablement, missing configuration, timeout, quota, malformed output, invalid percentages, rate limiting, or other provider errors return a typed degraded response containing deterministic fallback and never affect core endpoints.

## 9. Deployment and observability

- Build the derived dataset and model offline; runtime services are not training services.
- API starts only when required manifests/artifacts pass hash and schema checks.
- Log request ID, endpoint, latency, model/dataset version, and error class without raw data or secrets.
- Copilot logs include provider, configured model identifier, prompt version, cache status, latency, and outcome, never keys or full prompts.
- Health distinguishes core readiness from optional copilot availability.
- `FORECAST_BUST_DATA_ROOT` relocates historic absolute manifest paths beneath a configured runtime data root while preserving hash validation. Path escape and unmappable path failures are fatal.
- The root `Dockerfile` builds a non-root Python 3.11 API image and intentionally excludes `data/`. Run it with a read-only, license-cleared runtime artifact bundle mounted at `/app/data` and a writable Copilot cache path. `render.yaml` keeps auto-deploy off, checks `/health`, and leaves artifact root, CORS origin, Gemini model, and key as deployment-time values.
- `frontend/vercel.json` builds the Vite SPA to `dist`; production supplies only `VITE_API_BASE_URL`. No Gemini key or backend setting may use the public `VITE_` prefix.
- A hosted Render release is blocked until a private artifact-delivery mechanism and redistribution permission for the derived runtime bundle are confirmed. Deployment configuration must not bypass that license gate.
