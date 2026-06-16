# kvc

Key-Value Storage in C/C++.

## Goal

How far can I optimize an in-memory key-value store? Each version answers a
specific question, the benchmarks quantify the answer, and the next version
picks up from there.

## Versions

See [`VERSIONS.md`](VERSIONS.md) for the full list.

## Project layout

```
src/<version>/          one directory per implementation (e.g. v1_baseline)
bench/                  benchmark suite — orchestration, profiling, dashboard
tools/perf-orchestrator custom Python library for perf stat/record/flamegraph
CMakeLists.txt          top-level CMake build (all versions)
Makefile                convenience targets (format, lint, init)
```

[`tools/perf-orchestrator`](https://github.com/VincentNguyenDuc/perf-orchestrator)
is developed alongside this project but is generic and reusable.

## Build

Three presets are defined in [`CMakePresets.json`](CMakePresets.json):

| Preset | Flags | Output dir | Use for |
|--------|-------|------------|---------|
| `release` | `-O2 -DNDEBUG` | `build/release/` | production / distribution |
| `debug` | `-O0 -g` | `build/debug/` | debugging |
| `profile` | `-O2 -g -fno-omit-frame-pointer` | `build/profile/` | benchmarking + flamegraphs |

```bash
# Configure once per preset (only needed when CMakeLists.txt changes)
cmake --preset release
cmake --preset debug
cmake --preset profile

# Build all versions
cmake --build --preset release

# Build a single version (target = kvc_<version> with dots replaced by underscores)
cmake --build --preset release --target kvc_v1_baseline
cmake --build --preset debug   --target kvc_v2_better_hashmap
```

Binaries land at `build/<preset>/<version>/kvc`.

## Benchmarking

### Native (recommended for accurate perf counters)

```bash
python3 bench/main.py                                               # v1_baseline, 1 connection
python3 bench/main.py --connections 4 --requests 200000
python3 bench/main.py --version v2_better_hashmap --label "v2 run"
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
| `--env` | `native` | Environment tag (e.g. `Azure-Standard_D2s_v3`) |
| `--no-build` | | Skip build step (binary must already exist) |
| `--output` | auto | Output directory (defaults to `bench/output/<version>/<run-id>/`) |

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
