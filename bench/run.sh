#!/usr/bin/env bash
# Run the kvc benchmark inside a Docker container with a pinned environment.
#
# Flags consumed by this script (not forwarded to bench.py):
#   --with-perf        Attach perf stat + perf record to the server.
#                      Prints hardware counters (cache miss rate, IPC, …) in
#                      bench.py output, and a hot-path report via perf report.
#                      Requires Docker perf capabilities (added automatically).
#   --with-flamegraph  (implies --with-perf) Also generate a flamegraph SVG
#                      written to bench/output/ on the host.
#
# All other flags are forwarded verbatim to bench.py.
#
# Examples:
#   bench/run.sh
#   bench/run.sh --with-perf --requests 200000 --label "v1"
#   bench/run.sh --with-flamegraph --label "v1"
#   bench/run.sh --with-perf --connections 4 --json > results/v1.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/output"

IMAGE=kvc-bench
WITH_PERF=0
WITH_FLAMEGRAPH=0
BENCH_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-perf)        WITH_PERF=1; shift ;;
        --with-flamegraph)  WITH_PERF=1; WITH_FLAMEGRAPH=1; shift ;;
        *)                  BENCH_ARGS+=("$1"); shift ;;
    esac
done

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
echo "==> Building $IMAGE image..."
docker build --target bench -t "$IMAGE" "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Docker flags
# ---------------------------------------------------------------------------
DOCKER_FLAGS=(
    --cpuset-cpus 0-1
    --memory 1g
    --memory-swap 1g
)

if [[ $WITH_PERF -eq 1 ]]; then
    DOCKER_FLAGS+=(
        --cap-add=SYS_ADMIN
        --cap-add=PERFMON
        --security-opt seccomp=unconfined
    )
fi

if [[ $WITH_FLAMEGRAPH -eq 1 ]]; then
    mkdir -p "$OUTPUT_DIR"
    DOCKER_FLAGS+=(-v "$OUTPUT_DIR:/results")
fi

# ---------------------------------------------------------------------------
# Print environment summary
# ---------------------------------------------------------------------------
echo "==> Benchmark environment:"
echo "    CPUs     : 2 (server=core0, client=core1)"
echo "    Memory   : 1 GB, swap disabled"
echo "    Network  : loopback (127.0.0.1)"
echo "    perf     : $([ $WITH_PERF -eq 1 ] && echo enabled || echo disabled)"
echo "    flamegraph: $([ $WITH_FLAMEGRAPH -eq 1 ] && echo enabled || echo disabled)"
[[ ${#BENCH_ARGS[@]} -gt 0 ]] && echo "    bench args: ${BENCH_ARGS[*]}"
echo ""

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
docker run --rm \
    "${DOCKER_FLAGS[@]}" \
    -e _WITH_PERF="$WITH_PERF" \
    -e _WITH_FLAMEGRAPH="$WITH_FLAMEGRAPH" \
    "$IMAGE" \
    bash -c '
        set -euo pipefail

        # Start the server on core 0.
        taskset -c 0 ./build/kvc.o 8080 16384 > /tmp/server.log 2>&1 &
        SERVER_PID=$!

        # Wait until the server accepts connections.
        for _ in $(seq 1 50); do
            nc -z 127.0.0.1 8080 2>/dev/null && break
            sleep 0.1
        done

        cleanup() {
            kill "$SERVER_PID" 2>/dev/null || true
            wait "$SERVER_PID" 2>/dev/null || true
        }
        trap cleanup EXIT

        PERF_RECORD_PID=""
        PERF_DATA=/tmp/bench-perf.data

        if [[ "$_WITH_PERF" == "1" ]]; then
            # perf record collects call stacks for flamegraph + hot-path report.
            # Runs on core 0 alongside the server (same core is fine; it is a
            # sampling profiler and adds only a few percent overhead).
            perf record \
                -p "$SERVER_PID" \
                --call-graph dwarf \
                -F 99 \
                -o "$PERF_DATA" \
                > /dev/null 2>&1 &
            PERF_RECORD_PID=$!
        fi

        # Run the bench client on core 1.
        # Pass --perf-pid so bench.py attaches perf stat for hardware counters.
        EXTRA_ARGS=()
        [[ "$_WITH_PERF" == "1" ]] && EXTRA_ARGS=(--perf-pid "$SERVER_PID")

        taskset -c 1 python3 bench/bench.py "${EXTRA_ARGS[@]}" "$@"

        # ---------------------------------------------------------------------------
        # Post-benchmark perf analysis
        # ---------------------------------------------------------------------------
        if [[ -n "$PERF_RECORD_PID" ]]; then
            kill -INT "$PERF_RECORD_PID" 2>/dev/null || true
            wait "$PERF_RECORD_PID" 2>/dev/null || true

            printf "\n--- hot paths (top functions by server CPU time) ---\n"
            perf report \
                -i "$PERF_DATA" \
                --stdio \
                --no-children \
                -g none \
                2>/dev/null \
                | grep -v "^#" \
                | grep -v "^$" \
                | head -30 || true

            if [[ "$_WITH_FLAMEGRAPH" == "1" ]]; then
                FG_SCRIPT=tools/FlameGraph/stackcollapse-perf.pl
                FG_RENDER=tools/FlameGraph/flamegraph.pl
                if [[ -x "$FG_SCRIPT" && -x "$FG_RENDER" ]]; then
                    TS=$(date +%Y%m%d-%H%M%S)
                    FG_OUT=/results/flamegraph-$TS.svg
                    perf script -i "$PERF_DATA" \
                        | perl "$FG_SCRIPT" \
                        | perl "$FG_RENDER" > "$FG_OUT"
                    printf "\n==> Flamegraph: bench/results/flamegraph-%s.svg\n" "$TS"
                else
                    echo "warning: FlameGraph scripts not found (tools/FlameGraph/)" >&2
                fi
            fi
        fi
    ' -- "${BENCH_ARGS[@]+"${BENCH_ARGS[@]}"}"
