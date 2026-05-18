# kvc

Key-Value Storage

## Goal

How far can I optimize an in-memory Key-Value Storage?

## Project Layout

- `src/*.c` key-value storage implementation
- `bench/` benchmark suite — Docker orchestration, async workers, result files
- `tools/perf-orchestrator` — custom Python library for attaching `perf` capabilities to a subprocess lifecycle; 
  developed alongside this project but designed to be generic and reusable across projects

## Build

```bash
make
```

Artifacts are placed under `build/`.

## Benchmarking

### Run

```bash
make bench
```

Pass extra arguments via `BENCH_ARGS`:

```bash
make bench BENCH_ARGS="--requests 200000 --connections 4 --label 'v1 4-conn'"
```

Or call the script directly for full control:

```bash
bash bench/run.sh --requests 100000 --connections 1 --label "v1 baseline"
```

### Output

Each run writes results to `bench/output/<run-id>/`:

| File | Contents |
|------|----------|
| `bench.json` | Throughput, latency percentiles, op counts, hardware counters |
| `perf-report.txt` | Hot-path report from `perf report --stdio` |
| `flamegraph.svg` | Interactive flamegraph from `perf record` call stacks |
| `meta.json` | Run parameters, timestamp, git commit |

> **Note:** hardware counters (`perf stat`) require PMU support in the Docker VM.
> They may show zeros on some hosts (e.g. Docker Desktop on macOS).
> The hot-path report works regardless.
