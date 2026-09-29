from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import psutil

from .acquisition import AcquisitionStats, CountingGCSFileSystem, fetch_cycle_source_slices, fetch_ens_variable
from .source_cache import SourceSliceCache
from .constants import LEAD_HOURS
from .constants import DIAGNOSTICS, WEATHERBENCH_CACHE
from .corpus import _prepare_regions, derive_cycle_rows
from .exceptions import ValidationError
from .weatherbench import open_and_validate, open_mean_sources_and_validate, open_sources_and_validate


class _PeakMemory:
    def __init__(self):
        self.peak = psutil.Process().memory_info().rss
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self):
        process = psutil.Process()
        while not self._stop.wait(0.1):
            self.peak = max(self.peak, process.memory_info().rss)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()


def _artifact_size(artifacts: list[dict]) -> int:
    paths = {Path(item["data"]) for item in artifacts} | {Path(item["metadata"]) for item in artifacts}
    return sum(path.stat().st_size for path in paths if path.exists())


def run_benchmark(
    initialization: str = "2020-06-01T00:00:00",
    concurrency: int = 1,
    root: Path | None = None,
    cache_namespace: str | None = None,
) -> dict:
    if concurrency not in (1, 2, 4):
        raise ValidationError("concurrency must be one of 1, 2, or 4")
    filesystem = CountingGCSFileSystem()
    ens_mean, hres, _ = open_mean_sources_and_validate(filesystem=filesystem)
    init = np.datetime64(initialization, "ns")
    if cache_namespace and (not cache_namespace.replace("-", "").isalnum() or "/" in cache_namespace or "\\" in cache_namespace):
        raise ValidationError("cache_namespace must contain only letters, numbers, and hyphens")
    cache_root = root / "data/cache/weatherbench" if root else WEATHERBENCH_CACHE
    if cache_namespace:
        cache_root = cache_root.parent / cache_namespace
    weights, _, _, _, weights_dir = _prepare_regions(root, ens_mean)

    before_bytes, before_requests = filesystem.bytes_transferred, filesystem.request_count
    first_started = time.monotonic()
    with _PeakMemory() as memory:
        forecast, previous, state, precip, first_stats = fetch_cycle_source_slices(
            None, ens_mean, hres, init, cache_root=cache_root, concurrency=concurrency
        )
        first_rows, _ = derive_cycle_rows(forecast, previous, state, precip, weights, weights_dir, init)
    first_seconds = time.monotonic() - first_started
    first_bytes = filesystem.bytes_transferred - before_bytes
    first_requests = filesystem.request_count - before_requests

    second_before_bytes, second_before_requests = filesystem.bytes_transferred, filesystem.request_count
    second_started = time.monotonic()
    forecast2, previous2, state2, precip2, second_stats = fetch_cycle_source_slices(
        None, ens_mean, hres, init, cache_root=cache_root, concurrency=concurrency, cache_only=True
    )
    second_rows, _ = derive_cycle_rows(forecast2, previous2, state2, precip2, weights, weights_dir, init)
    second_seconds = time.monotonic() - second_started
    second_bytes = filesystem.bytes_transferred - second_before_bytes
    second_requests = filesystem.request_count - second_before_requests
    if not first_rows.equals(second_rows):
        raise ValidationError("Cached and uncached benchmark rows differ")

    cache_size = _artifact_size(first_stats.artifacts)
    report = {
        "initialization": str(init),
        "concurrency": concurrency,
        "feature_contract": "mean-only-mvp-v2",
        "raw_ensemble_member_access": False,
        "first_run": {
            "wall_seconds": first_seconds,
            "actual_bytes_transferred": first_bytes,
            "remote_requests": first_requests,
            "cache_hits": first_stats.cache_hits,
            "cache_misses": first_stats.cache_misses,
            "derived_rows": first_rows.height,
            "peak_rss_bytes": memory.peak,
        },
        "second_run": {
            "wall_seconds": second_seconds,
            "actual_bytes_transferred": second_bytes,
            "remote_requests": second_requests,
            "cache_hits": second_stats.cache_hits,
            "cache_misses": second_stats.cache_misses,
            "derived_rows": second_rows.height,
            "identical_rows": True,
        },
        "cache_size_bytes": cache_size,
        "projection": {"command": "forecast-bust project-acquisition", "note": "Full projection deduplicates shared prior-cycle and HRES source chunks; do not multiply this benchmark naively."},
    }
    output = (root / "data/diagnostics" if root else DIAGNOSTICS) / "weatherbench-benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    report["report"] = str(output)
    return report


def benchmark_concurrency(initialization: str = "2020-06-01T12:00:00", root: Path | None = None) -> dict:
    results = []
    init = np.datetime64(initialization, "ns")
    base_cache = root / "data/cache/weatherbench-concurrency" if root else WEATHERBENCH_CACHE.parent / "weatherbench-concurrency"
    for concurrency in (1, 2, 4):
        filesystem = CountingGCSFileSystem()
        ens, _, _ = open_and_validate(filesystem=filesystem)
        run_cache = base_cache / f"run-{uuid.uuid4().hex}" / f"concurrency={concurrency}"
        cache = SourceSliceCache(run_cache)
        stats = AcquisitionStats()
        before_bytes, before_requests = filesystem.bytes_transferred, filesystem.request_count
        started = time.monotonic()
        fetch_ens_variable(
            ens,
            cache,
            "mean_sea_level_pressure",
            init,
            tuple(LEAD_HOURS),
            concurrency=concurrency,
            stats=stats,
        )
        elapsed = time.monotonic() - started
        transferred = filesystem.bytes_transferred - before_bytes
        results.append(
            {
                "concurrency": concurrency,
                "wall_seconds": elapsed,
                "bytes_transferred": transferred,
                "requests": filesystem.request_count - before_requests,
                "throughput_bytes_per_second": transferred / elapsed,
                "cache_misses": stats.cache_misses,
            }
        )
    fastest = max(item["throughput_bytes_per_second"] for item in results)
    acceptable = [item for item in results if item["throughput_bytes_per_second"] >= fastest * 0.75]
    selected = min(item["concurrency"] for item in acceptable)
    report = {"initialization": str(init), "variable": "mean_sea_level_pressure", "lead_hours": list(LEAD_HOURS), "results": results, "selected_concurrency": selected, "selection_rule": "lowest concurrency within 75% of the best measured throughput"}
    output = (root / "data/diagnostics" if root else DIAGNOSTICS) / "weatherbench-concurrency.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    report["report"] = str(output)
    return report
