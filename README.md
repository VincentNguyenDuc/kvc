# kvc

Key-Value Storage - Performance Engineering Playground

## Goal

How far can I optimize an in-memory Key-Value Storage?

## Protocol

Commands (one per line):

- `SET <key> <value>`
- `GET <key>`
- `DEL <key>`

Responses:

- `OK`
- `VALUE <value>`
- `NOT_FOUND`
- `ERROR`

## Project Layout

- `src/*.c` key-value storage implementation
- `bench/` benchmark suite — Docker orchestration, async workers, result files
- `tools/perf-orchestrator` — custom Python library for attaching `perf` capabilities to a subprocess lifecycle; 
  implemented alongside this project but designed to be generic and reusable across projects

## Build

```bash
make
```

Artifacts are placed under `build/`.

## Formatting

Format all C and header files:

```bash
make format
```

Check formatting without modifying files:

```bash
make format-check
```

## Run

```bash
./build/kvc.o
```

Optional args:

```bash
./build/kvc.o <port> <hashmap_buckets>
```

Defaults:

- `port=8080`
- `hashmap_buckets=1024`

## Quick Manual Test

In terminal 1:

```bash
./build/kvc.o
```

In terminal 2:

```bash
nc localhost 8080
SET foo hello
GET foo
DEL foo
GET foo
```

Expected responses:

```text
OK
VALUE hello
OK
NOT_FOUND
```

## Benchmarking

Benchmarks run inside a Docker container for a consistent, reproducible environment:

| Parameter | Value |
|-----------|-------|
| CPUs available | 2 (host cores 0–1 via `--cpuset-cpus`) |
| Server CPU | core 0 (via `taskset`) |
| Client CPU | core 1 (via `taskset`) |
| RAM | 1 GB (`--memory 1g`) |
| Swap | disabled (`--memory-swap 1g`) |
| Network | loopback (`127.0.0.1`) — no NIC variance |
| Hashmap buckets | 16384 |

Perf is always enabled: `perf stat` (hardware counters) and `perf record` (call-stack sampling) are attached to the server process for every run.

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

### Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--label` | — | Human-readable label for this run |
| `--requests` | 100000 | Total operations (split evenly across connections) |
| `--connections` | 1 | Concurrent TCP connections |
| `--warmup` | 1000 | Requests sent before timing starts |
| `--key-space` | 10000 | Number of unique keys |
| `--value-size` | 64 | Value size in bytes |
| `--set-ratio` | 0.15 | Fraction of SET operations |
| `--del-ratio` | 0.05 | Fraction of DEL operations |
| `--no-build` | false | Skip Docker image build (use cached image) |

The remaining fraction (`1 - set-ratio - del-ratio`) is GET operations. The default workload is **80% GET / 15% SET / 5% DEL**.

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

### Profiling build

`make profile-build` compiles with debug symbols and frame pointers (`-g -fno-omit-frame-pointer`) for use outside the bench Docker environment.
