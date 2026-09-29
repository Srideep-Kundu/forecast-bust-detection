from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from .api import create_app
from .constants import DATA, REPORTS


def benchmark_api(data_root: Path = DATA) -> dict:
    started = time.perf_counter()
    app = create_app(data_root)
    startup_ms = (time.perf_counter() - started) * 1000
    client = TestClient(app)
    run = client.get("/v1/runs").json()[0]
    region = client.get("/v1/regions").json()[0]
    endpoints = {
        "risk_map": f"/v1/risk-map?run_id={run['run_id']}&lead_day=1",
        "lead_curve": f"/v1/regions/{region['region_id']}/lead-curve?run_id={run['run_id']}",
    }
    risk = client.get(endpoints["risk_map"]).json()["risks"][0]
    endpoints["explanation"] = f"/v1/predictions/{risk['prediction_id']}/explanation"
    timings = {}
    for name, url in endpoints.items():
        samples = []
        for _ in range(5):
            before = time.perf_counter()
            response = client.get(url)
            response.raise_for_status()
            samples.append((time.perf_counter() - before) * 1000)
        timings[name] = {"median_ms": sorted(samples)[2], "samples_ms": samples}
    result = {"startup_ms": startup_ms, "run_id": run["run_id"], "region_id": region["region_id"], "prediction_id": risk["prediction_id"], "timings": timings}
    output = data_root / "reports/api-benchmark.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return result
