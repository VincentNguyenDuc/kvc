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

- `src/main.c` CLI entry point
- `src/server.c` TCP + epoll event loop
- `src/protocol.c` request parsing
- `src/hashmap.c` in-memory key/value store

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

Benchmarks run inside a Docker container for a consistent, reproducible environment. The setup is:

| Parameter | Value |
|-----------|-------|
| CPUs available | 2 (host cores 0–1 via `--cpuset-cpus`) |
| Server CPU | core 0 (via `taskset`) |
| Bench client CPU | core 1 (via `taskset`) |
| RAM | 1 GB (`--memory 1g`) |
| Swap | disabled (`--memory-swap 1g`) |
| Network | loopback (`127.0.0.1`) — no NIC variance |
| Hashmap buckets | 16384 |

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
python bench/run.py --requests 100000 --connections 1 --label "v1 baseline"
```

### Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--requests` | 100000 | Total operations (split evenly across connections) |
| `--connections` | 1 | Concurrent TCP connections |
| `--warmup` | 1000 | Requests sent before timing starts |
| `--key-space` | 10000 | Number of unique keys |
| `--value-size` | 64 | Value size in bytes |
| `--set-ratio` | 0.15 | Fraction of SET operations |
| `--del-ratio` | 0.05 | Fraction of DEL operations |
| `--json` | false | Emit JSON output instead of text |
| `--label` | — | Label printed in the report |

The remaining fraction (`1 - set-ratio - del-ratio`) is GET operations. The default workload is **80% GET / 15% SET / 5% DEL**.

### Example output

```
connections : 1
requests    : 100,000  (errors: 0)
op mix      : GET=79,872  SET=15,043  DEL=5,085
duration    : 4.231 s
throughput  : 23,638 ops/sec
latency us  : min=28.4  p50=39.1  p95=52.3  p99=71.8  p999=124.6  max=891.2
```

### Comparing versions

Use `--label` and `--json` to capture results for each version:

```bash
python bench/run.py --label "v1" --json > results/v1.json
python bench/run.py --label "v2" --json > results/v2.json
```

### Profiling (hardware counters + flamegraph)

Pass `--with-perf` to enable server-side profiling alongside the benchmark:

```bash
python bench/run.py --with-perf --label "v1"
```

This adds Docker perf capabilities, attaches `perf stat` to the server process via
the bench package, and runs `perf record` in parallel. After the benchmark you get:

- Hardware counters: cache miss rate, IPC, CPI, branch miss rate
- Hot-path report: top functions by CPU time (`perf report --stdio`)

Add `--with-flamegraph` to also generate an interactive SVG in `bench/output/`:

```bash
python bench/run.py --with-flamegraph --label "v1"
```

> **Note:** hardware counters (`perf stat`) require PMU support in the Docker VM.
> They may show zeros on some hosts (e.g. Docker Desktop on macOS). The hot-path
> report and flamegraph work regardless.

The `perf/tools/FlameGraph/` scripts are used for SVG generation.
`make profile-build` builds the server with debug symbols and frame pointers for
use outside the bench Docker environment.
