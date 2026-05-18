# kvc

Key-Value Storage

## Goal

How far can I optimize an in-memory Key-Value Storage?

## Project Layout

- `src/<version>/` — one directory per implementation (e.g. `v1_baseline`)
- `bench/` — benchmark suite
- [`tools/perf-orchestrator`](https://github.com/VincentNguyenDuc/perf-orchestrator) — custom Python library for attaching `perf` capabilities; developed alongside this project but designed to be generic and reusable across projects

## Build

```bash
make                        # builds v1_baseline (default)
make VERSION=v2_foo         # builds a specific version
```

Artifacts are placed under `build/<version>/kvc.o`.

## Benchmarking

### Run

```bash
make bench                                    # benchmark v1_baseline
make bench BENCH_ARGS="--version v2_foo"      # benchmark a specific version
```

Or call the script directly for full control:

```bash
bash bench/run.sh --version v1_baseline --requests 200000 --connections 4 --label "baseline"
bash bench/run.sh --version v2_foo      --requests 200000 --connections 4 --label "v2 attempt"
```

### Output

Each run writes results to `bench/output/<version>/<run-id>/`:

| File              | Contents                                                      |
| ----------------- | ------------------------------------------------------------- |
| `bench.json`      | Throughput, latency percentiles, op counts, hardware counters |
| `perf-report.txt` | Hot-path report from `perf report --stdio`                    |
| `flamegraph.svg`  | Interactive flamegraph from `perf record` call stacks         |
| `meta.json`       | Run parameters, version, timestamp, git commit                |

> **Note:** hardware counters (`perf stat`) require PMU support in the Docker VM.
> They may show zeros on some hosts (e.g. Docker Desktop on macOS).
> The hot-path report works regardless.
