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

## Profiling (perf + FlameGraph)

Profiling scripts live in `perf/`:

- `perf/check.sh` preflight for perf permissions
- `perf/record.sh` captures `perf.data` while running a workload
- `perf/workload.sh` default mixed GET/SET/DEL load
- `perf/flamegraph.sh` generates SVG flamegraph

Run the full profiling flow (profile-friendly build, perf capture, flamegraph generation):

```bash
make perf-profile
```

This writes:

- `build/perf/perf.data`
- `build/perf/flamegraph.svg`
- `build/perf/server.log`

Run individual steps:

```bash
make profile-build
make perf-check
make perf-record
make perf-flamegraph
```

If `make perf-check` fails with `Operation not permitted` in a container, start the dev container with perf capabilities, for example:

```text
--cap-add=SYS_ADMIN --cap-add=PERFMON --security-opt seccomp=unconfined
```

You can also lower `kernel.perf_event_paranoid` on the host.
