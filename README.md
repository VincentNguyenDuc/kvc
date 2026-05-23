# kvc

Key-Value Storage in C.

## Goal

How far can I optimize an in-memory key-value store? Each version answers a
specific question, the benchmarks quantify the answer, and the next version
picks up from there.

## Project layout

```
src/<version>/          one directory per implementation (e.g. v1_baseline)
bench/                  benchmark suite — orchestration, profiling, dashboard
tools/perf-orchestrator custom Python library for perf stat/record/flamegraph
```

[`tools/perf-orchestrator`](https://github.com/VincentNguyenDuc/perf-orchestrator)
is developed alongside this project but is generic and reusable.

## Build

```bash
make                      # build v1_baseline (default)
make VERSION=v2_foo       # build a specific version
```

Artifacts land in `build/<version>/kvc`.

## Benchmarking

### Native (recommended for accurate perf counters)

```bash
python3 bench/main.py                                  # v1_baseline, 1 connection
python3 bench/main.py --connections 4 --requests 200000
python3 bench/main.py --version v2_foo --label "v2 attempt"
```

Output is auto-generated under `bench/output/<version>/<run-id>/`.

Key options:

| Flag | Default | Description |
|------|---------|-------------|
| `--version` | `v1_baseline` | Which implementation to benchmark |
| `--connections` | `1` | Concurrent client connections |
| `--requests` | `100000` | Total requests to send |
| `--warmup` | `1000` | Requests before measurement starts |
| `--key-space` | `10000` | Number of distinct keys |
| `--value-size` | `64` | Value size in bytes |
| `--set-ratio` | `0.15` | Fraction of SET operations |
| `--del-ratio` | `0.05` | Fraction of DEL operations |
| `--label` | | Human-readable run label |
| `--env` | `native` | Environment tag (e.g. `docker`, `Azure-Standard_D2s_v3`) |
| `--no-build` | | Skip `make` (binary must already exist) |
| `--output` | auto | Output directory (defaults to `bench/output/<version>/<run-id>/`) |

### Docker

```bash
bash bench/docker.sh
```

Builds a Linux container, runs the full pipeline with `--cpuset-cpus 0-1`,
writes results to `bench/output/`.

### Azure

```bash
bash bench/azure.sh
```

Provisions a VM, runs the benchmark remotely, and syncs results back.

### Output

Each run writes to `bench/output/<version>/<run-id>/`:

| File | Contents |
|------|----------|
| `bench.json` | All results: throughput, latency percentiles, op counts, perf counters, infra info, run config |
| `flamegraph.svg` | Interactive flamegraph from `perf record` call stacks |

> **Note:** hardware counters (`perf stat`) require PMU access.
> They may be unavailable inside containers or cloud VMs.
> Software counters (task-clock, context-switches, page-faults) always work.

## Dashboard

```bash
pip install -r bench/requirements.txt
streamlit run bench/dashboard.py
```

Interactive Streamlit dashboard with Overview, Trends, Compare, and About tabs.
Auto-reloads from `bench/output/` every 30 seconds.
