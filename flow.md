# Forecast Bust Detection Application Flow

## Priority and trust boundary

P0 is the complete scientific product. P1 GenAI is a downstream explanation convenience and may be disabled. XGBoost is the only authoritative bust-risk model.

```mermaid
flowchart LR
    WB[WeatherBench 2] --> FE[Feature Engineering]
    FE --> XGB[XGBoost]
    XGB --> CAL[Probability Calibration]
    CAL --> BP[Bust Probability]
    BP --> EA[SHAP + Historical Analogs]
    EA --> DASH[Dashboard]

    EA --> CTX[Approved Evidence + Prediction Metadata]
    CTX --> AI[Optional GenAI Copilot]
    AI --> NL[Natural-Language Explanation]
    NL --> DASH

    classDef science fill:#d6e4ff,stroke:#0f62fe,color:#161616;
    classDef optional fill:#f4f4f4,stroke:#8d8d8d,color:#161616,stroke-dasharray: 5 5;
    class WB,FE,XGB,CAL,BP,EA,DASH science;
    class CTX,AI,NL optional;
```

The dashed branch consumes finished evidence. It cannot write to the scientific path.

## Offline dataset flow

```mermaid
flowchart TD
    A[Open official IFS ENS mean and HRES metadata] --> B{Variables, units, dimensions and coordinates valid?}
    B -- No --> X[Fail loudly]
    B -- Yes --> C[Normalize coordinates and longitude]
    C --> D{Grids exactly aligned?}
    D -- Yes --> E[Exact coordinate alignment]
    D -- No --> F[Build and persist xESMF weights]
    F --> G{Regridding reproducible?}
    G -- No --> X
    G -- Yes --> H[Aligned HRES grid]
    E --> H
    H --> I[Validate intended 36-region manifest and geometry]
    I --> J{Count, names, IDs, CRS, validity, topology pass?}
    J -- No --> X
    J -- Yes --> R[Record explicit make_valid repairs and <=5 km2 source slivers]
    R --> K[Build geodesic cell-region weights]
    K --> L{Weights finite and sum to 1?}
    L -- No --> X
    L -- Yes --> M[Select monsoon dates and exact 24-240h leads]
    M --> FM[Official ENS mean for all P0 forecast fields]
    FM --> CCH[Atomic checksummed India source-slice cache]
    H --> CCH
    CCH --> N[Cache-only grid derivatives and verification errors]
    N --> O[Regional aggregation]
    O --> P[Atomically write 360-row initialization partition]
    P --> Q{All expected 00/12 cycles present?}
    Q -- No --> M
    Q -- Yes --> Z[Write complete manifest, gaps, row counts, hashes]
```

The production flow has no raw-member edge. Optional post-MVP research mode may acquire full-member spread separately, but it is not part of the P0 schema or ML gate. Deterministic run-to-run drift, lead time, gradients, vorticity, and precipitation magnitude must not be labeled as ensemble spread. Downstream context retains only explicit approved feature values and optional run-to-run drift.

The mean-only feature stage emits 2 m temperature, MSLP, 10 m u/v and wind speed, 850 hPa wind/vorticity, 500-850 hPa thickness, 24-hour precipitation, MSLP gradient, run-to-run drift, lead day, seasonal encoding, and categorical region ID.

## Training, calibration, and evaluation

```mermaid
flowchart LR
    D[Derived rows] --> S{Initialization year}
    S -->|2018-2020| TR[Training]
    S -->|2021| VA[Validation and calibration]
    S -->|2022| TE[Untouched test]

    TR --> ST[Fit robust stats and q85 thresholds]
    ST --> LP[Write labeled year/month partitions]
    LP --> PRE[Fit preprocessing and categorical encoder]
    PRE --> HP[Fit/select XGBoost using 2021 PR-AUC]
    HP --> RF[Refit selected classifier on 2018-2020 only]
    RF --> VP[Predict 2021]
    VP --> PC[Fit sigmoid calibrator]
    RF --> TP[Predict 2022]
    PC --> TP
    TP --> MET[PR-AUC, ROC-AUC, Brier, BSS, ECE, top-20 recall, slices]
    TR --> BL[Fit climatology + deterministic logistic baseline]
    RF --> SHAP[SHAP]
    ST --> ANA[Training-only analog index]
```

No arrow returns from validation or test data to training statistics or classifier fitting.

## Runtime application flow

```mermaid
flowchart LR
    A[Choose Forecast Run] --> B[Select Lead Day]
    B --> C[Inspect Risk Map]
    C --> D[Select Region]
    D --> E[Inspect Lead-Risk Curve]
    E --> F[Review SHAP Drivers]
    F --> G[Review Historical Analogs]
    G -. P1 only .-> H[Ask AI Copilot]
```

At every step, retain `run_id`, `prediction_id`, source time, valid time, model version, dataset version, and provenance.

The implemented dashboard continues from deterministic SHAP and analog evidence into the secondary P1 panel. The dashed P1 step is optional, resets whenever prediction identity changes, and is never required for P0 runtime.

```mermaid
flowchart TD
    BOOT[Load health, model, runs, regions and geometry] --> RUN[Default to latest verified run]
    RUN --> MAP[Fetch run + lead risk map]
    MAP --> JOIN[Join 36 risks to canonical GeoJSON by region_id]
    JOIN --> PICK[Select subdivision]
    PICK --> PAR[Fetch lead curve and explanation in parallel]
    PAR --> VIEW[Render reliability, curve, SHAP and analogs]
    VIEW -. optional user question .-> COP[Copilot panel]
    MAP -. panel failure .-> PM[Typed map state; retain other panels]
    PAR -. panel failure .-> PE[Typed evidence state; retain map and curve]
```

## Prediction request

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Dashboard
    participant API as FastAPI
    participant DS as DuckDB/Artifacts

    U->>UI: Select run and lead
    UI->>API: GET /v1/risk-map
    API->>DS: Query verified held-out prediction Parquet
    DS-->>API: RegionRisk records
    API-->>UI: Risk map + provenance
    U->>UI: Select subdivision
    UI->>API: GET lead-curve and explanation
    API->>DS: Query prediction + allowed forecast features
    DS-->>API: Frozen classifier, calibrator, scaler, training candidates
    API->>API: Validate calibrated probability
    API->>API: Exact TreeSHAP in saved transformed space
    API->>API: Same-region/same-lead analog rank; deterministic fallback
    API-->>UI: Evidence panels
```

Runtime identity is deterministic: `run-YYYYMMDDTHHMMSSZ` and `<model_version>__YYYYMMDDTHHMMSSZ__imd-NN__dNN`. The API validates hashes and schemas before serving. Geometry references resolve through `GET /v1/regions/geojson`; scientific responses come only from saved real-data artifacts.

## Copilot request and graceful failure

```mermaid
sequenceDiagram
    participant UI as Dashboard
    participant API as FastAPI
    participant EV as Evidence Store
    participant LLM as LLM Provider

    UI->>API: POST /v1/copilot/query
    API->>EV: Load prediction evidence
    EV-->>API: Approved CopilotContext fields
    API->>API: Typed allowlist, serialize untrusted data, build versioned cache key
    alt Valid cache hit
        API-->>UI: Cached answer + grounding + versions
    else Provider enabled
        API->>API: Apply process-local rate limit
        API->>LLM: Immutable prompt + typed CopilotContext
        LLM-->>API: Candidate narrative
        API->>API: Validate numbers and event/causality claims; retry once
        API-->>UI: Answer + deterministic evidence
    else Disabled, timeout, quota, or error
        API->>API: Build deterministic probability/SHAP/analog summary
        API-->>UI: Degraded response + grounding + versions
        UI->>UI: Show warning and keep every P0 panel visible
    end
```

Only successful provider narratives enter the bounded hashed SQLite cache. Disabled and failure fallbacks are not cached as provider answers. The cache key includes prediction, normalized-question hash, mode, scientific model and dataset versions, prompt version, provider, and provider model.

## UI states

| State | Required behavior |
|---|---|
| Loading | Layout-matched skeletons; do not show stale values as current |
| Empty | Explain that no versioned run/lead data is available |
| Partial | Identify missing regions/evidence and retain valid records |
| Stale | Show source forecast time and explicit stale indicator |
| Core API error | Contextual retry and request ID |
| Copilot unavailable | Show the fixed unavailable message; retain all P0 evidence |

All replay timestamps are displayed as UTC. Responsive layouts collapse to one column without changing query parameters, selected identifiers, probabilities, or evidence.

## Change control

Any change to a dataset field, feature meaning, unit, entity, endpoint, response field, or copilot allowlist requires synchronized updates to `prd.md`, `tech.md`, `flow.md`, `agents.md`, and `README.md`.
