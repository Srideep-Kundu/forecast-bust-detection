from __future__ import annotations

import argparse
import json

from .pipeline import run_smoke
from .weatherbench import open_mean_sources_and_validate


def main() -> None:
    parser = argparse.ArgumentParser(prog="forecast-bust")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("cloud-check", help="Validate anonymous WeatherBench metadata access")
    smoke = subcommands.add_parser("smoke", help="Generate the minimal real-data Parquet slice and manifest")
    smoke.add_argument("--initialization", default="2020-06-01T00:00:00")
    smoke.add_argument("--lead-hours", type=int, default=24)
    full = subcommands.add_parser("build-full", help="Build/resume the complete 2018-2022 monsoon corpus")
    full.add_argument("--max-cycles", type=int, default=None, help="Stop after N newly completed cycles (for operational batching)")
    full.add_argument("--concurrency", type=int, choices=(1, 2, 4), default=1)
    fetch = subcommands.add_parser("fetch-source-slices", help="Fetch and atomically cache source chunks for one initialization")
    fetch.add_argument("--initialization", default="2020-06-01T00:00:00")
    fetch.add_argument("--concurrency", type=int, choices=(1, 2, 4), default=1)
    derived = subcommands.add_parser("build-derived", help="Build one derived partition strictly from verified local source cache")
    derived.add_argument("--initialization", default="2020-06-01T00:00:00")
    derived.add_argument("--concurrency", type=int, choices=(1, 2, 4), default=1)
    diagnosis = subcommands.add_parser("diagnose-reads", help="Write the per-variable WeatherBench Zarr read plan")
    diagnosis.add_argument("--initialization", default="2020-06-01T00:00:00")
    diagnosis.add_argument("--lead-hours", type=int, default=24)
    diagnosis.add_argument("--measure", action="store_true")
    diagnosis.add_argument("--concurrency", type=int, choices=(1, 2, 4), default=1)
    benchmark = subcommands.add_parser("benchmark-acquisition", help="Benchmark one ten-lead initialization and cached rerun")
    benchmark.add_argument("--initialization", default="2020-06-01T00:00:00")
    benchmark.add_argument("--concurrency", type=int, choices=(1, 2, 4), default=1)
    benchmark.add_argument("--cache-namespace", default=None, help="Optional isolated cache namespace for a cold benchmark")
    concurrency_benchmark = subcommands.add_parser("benchmark-concurrency", help="Compare conservative GCS concurrency 1, 2, and 4")
    concurrency_benchmark.add_argument("--initialization", default="2020-06-01T12:00:00")
    subcommands.add_parser("project-acquisition", help="Project unique full-corpus chunks, transfer, cache, and runtime")
    layout = subcommands.add_parser("assess-source-layout", help="Compare exact compressed object bytes for old and optimized layouts")
    layout.add_argument("--initialization", default="2020-06-01T00:00:00")
    spread = subcommands.add_parser("benchmark-spread-strategies", help="Compare exact mean/spread acquisition configurations")
    spread.add_argument("--initialization", default="2020-06-01T00:00:00")
    spread.add_argument("--reuse-existing", action="store_true", help="Refresh the persisted comparison without remote metadata access")
    subcommands.add_parser("verify-source-cache", help="Verify and upgrade source-slice cache provenance metadata")
    subcommands.add_parser("label", help="Fit training-only robust label artifacts and label the corpus")
    subcommands.add_parser("train", help="Train baselines, XGBoost, calibration, and evaluate 2021/2022")
    subcommands.add_parser("build-evidence", help="Fit and hash the training-only analog scaler")
    api = subcommands.add_parser("api", help="Run the read-only FastAPI historical-replay service")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    subcommands.add_parser("benchmark-api", help="Benchmark startup and core real-data API endpoints")
    gate = subcommands.add_parser("ml-gate", help="Run corpus build, labeling, training, and evaluation")
    gate.add_argument("--max-cycles", type=int, default=None)
    args = parser.parse_args()
    if args.command == "cloud-check":
        _, _, report = open_mean_sources_and_validate()
        print(json.dumps(report, indent=2, default=str))
    elif args.command == "smoke":
        print(json.dumps(run_smoke(args.initialization, args.lead_hours), indent=2))
    elif args.command == "build-full":
        from .corpus import build_full_corpus

        print(json.dumps(build_full_corpus(max_cycles=args.max_cycles, concurrency=args.concurrency), indent=2))
    elif args.command == "fetch-source-slices":
        from .corpus import fetch_source_slices

        print(json.dumps(fetch_source_slices(args.initialization, args.concurrency), indent=2))
    elif args.command == "build-derived":
        from .corpus import build_derived

        print(json.dumps(build_derived(args.initialization, args.concurrency), indent=2))
    elif args.command == "diagnose-reads":
        from .diagnostics import build_read_plan

        print(json.dumps(build_read_plan(args.initialization, args.lead_hours, args.measure, args.concurrency), indent=2))
    elif args.command == "benchmark-acquisition":
        from .benchmark import run_benchmark

        print(json.dumps(run_benchmark(args.initialization, args.concurrency, cache_namespace=args.cache_namespace), indent=2))
    elif args.command == "benchmark-concurrency":
        from .benchmark import benchmark_concurrency

        print(json.dumps(benchmark_concurrency(args.initialization), indent=2))
    elif args.command == "project-acquisition":
        from .projection import project_full_corpus

        print(json.dumps(project_full_corpus(), indent=2))
    elif args.command == "assess-source-layout":
        from .layout_assessment import assess_source_layout

        print(json.dumps(assess_source_layout(args.initialization), indent=2))
    elif args.command == "benchmark-spread-strategies":
        from .spread_strategy import compare_spread_strategies

        print(json.dumps(compare_spread_strategies(args.initialization, reuse_existing=args.reuse_existing), indent=2))
    elif args.command == "verify-source-cache":
        from .constants import WEATHERBENCH_CACHE
        from .source_cache import upgrade_cache_metadata

        print(json.dumps(upgrade_cache_metadata(WEATHERBENCH_CACHE), indent=2))
    elif args.command == "label":
        from .labels import label_full_corpus

        print(json.dumps(label_full_corpus(), indent=2))
    elif args.command == "train":
        from .modeling import train_and_evaluate

        print(json.dumps(train_and_evaluate(), indent=2))
    elif args.command == "build-evidence":
        from .evidence import build_analog_artifacts

        print(json.dumps(build_analog_artifacts(), indent=2))
    elif args.command == "api":
        import uvicorn

        uvicorn.run("forecast_bust.api:app", host=args.host, port=args.port, reload=False)
    elif args.command == "benchmark-api":
        from .api_benchmark import benchmark_api

        print(json.dumps(benchmark_api(), indent=2))
    elif args.command == "ml-gate":
        from .corpus import build_full_corpus
        from .labels import label_full_corpus
        from .modeling import train_and_evaluate

        corpus = build_full_corpus(max_cycles=args.max_cycles)
        if corpus["status"] != "complete":
            raise SystemExit(json.dumps({"corpus": corpus, "status": "incomplete; resume ml-gate"}, indent=2))
        print(json.dumps({"corpus": corpus, "labels": label_full_corpus(), "model": train_and_evaluate()}, indent=2))


if __name__ == "__main__":
    main()
