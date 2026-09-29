# WeatherBench read diagnosis

Reference initialization: `2020-06-01T00:00:00Z`; reference lead: `+24h`.

## Root cause

The 1.5-degree IFS ENS Zarr arrays are chunked as one initialization, all 50 members, eight lead times, and the full `240 x 121` global grid. Pressure variables additionally store all three levels in the same chunk. Selecting India, one lead, or one pressure level therefore still transfers each complete compressed object.

For one initialization and one lead, the required fields intersect `702,535,680` uncompressed source bytes. The counting GCS filesystem measured `526,713,847` transferred bytes across 15 objects.

Reading the ten leads separately would re-read shared eight-lead chunks. Batched/native-chunk access intersects six unique lead chunks per variable instead of ten.

## Implemented access layout

The optimized pipeline uses the official WeatherBench 2 IFS ENS mean product on the same `240 x 121` grid for deterministic means. The full 50-member product remains authoritative for the four required spread fields: MSLP, 10 m u wind, 10 m v wind, and 24-hour precipitation. For the reference initialization, all eight official mean fields were bit-for-bit equal to means computed from the 50 cached members.

Exact compressed object sizes for the ten-lead reference cycle:

- Previous full-member layout: `3,255,481,945` bytes across 80 objects.
- Optimized hybrid layout: `960,180,433` bytes across 104 objects.
- Reduction: `2,295,301,512` bytes (`70.51%`).

Every source object is reduced to the India domain and required pressure levels, then committed as a checksummed NetCDF plus JSON metadata under `data/cache/weatherbench/`. Metadata is the atomic commit marker. HRES native time chunks and prior-cycle mean MSLP chunks are shared across initialization cycles.

## Benchmark

- Optimized mean-layer fetch during the measured warm-cache transition: `63,538,420` bytes in `106.141` seconds.
- Reconstructed optimized cold-cycle source transfer: `960,180,433` bytes.
- Estimated optimized cold-cycle runtime: `362.65` seconds at measured raw-chunk throughput and mean-object latency.
- Cache-only rerun: `1.531` seconds, zero remote requests, zero transferred bytes.
- Derived rows: 360 on both runs; rows were identical.
- Reference cache size: `17,503,776` bytes.
- Peak RSS: `1,431,793,664` bytes.

Concurrency 1, 2, and 4 transferred the same six MSLP objects. Timings were 45.266 s, 60.093 s, and 43.547 s. Concurrency 1 remains the default because it is the lowest setting within 75% of the best measured throughput and avoids aggressive GCS access.

## Full-corpus projection

Accounting for unique chunk reuse across all 1,220 cycles:

- Projected compressed transfer: `1,151,249,040,212` bytes (about 1.15 TB decimal).
- Projected local cache: `20,705,806,344` bytes (about 20.7 GB decimal).
- Projected runtime: `423,675` seconds (about 4.90 days) on this workstation.

This remains impractical for the available environment. No full-corpus run was started. The remaining blocker is the full-global/member chunk layout for the four spread variables; the official catalog does not provide an equivalent precomputed ensemble-standard-deviation product.

Machine-readable evidence is in `weatherbench-read-plan.json`, `weatherbench-source-layout.json`, `weatherbench-concurrency.json`, `weatherbench-benchmark.json`, and `weatherbench-projection.json`. The official dataset catalog is documented at <https://weatherbench2.readthedocs.io/en/latest/data-guide.html>.
