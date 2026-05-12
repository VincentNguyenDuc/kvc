#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <binary> <out-dir> [port]" >&2
    exit 1
fi

BIN="$1"
OUT_DIR="$2"
PORT="${3:-8080}"
WORKLOAD_TIMEOUT_S="${WORKLOAD_TIMEOUT_S:-60}"

if [[ ! -x "$BIN" ]]; then
    echo "Binary not executable: $BIN" >&2
    exit 1
fi

if ! command -v perf >/dev/null 2>&1; then
    echo "perf is required but not installed" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
PERF_DATA="$OUT_DIR/perf.data"
SERVER_LOG="$OUT_DIR/server.log"

# Start server under perf and capture call stacks at 99Hz.
perf record -F 99 -g -o "$PERF_DATA" -- "$BIN" "$PORT" 1024 >"$SERVER_LOG" 2>&1 &
PERF_PID=$!

cleanup() {
    if kill -0 "$PERF_PID" >/dev/null 2>&1; then
        kill "$PERF_PID" >/dev/null 2>&1 || true
        wait "$PERF_PID" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# Wait until server is ready.
ready=0
for _ in $(seq 1 50); do
    if nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 0.1
done

if [[ "$ready" -ne 1 ]]; then
    echo "server did not become ready on port $PORT" >&2
    exit 1
fi

timeout "$WORKLOAD_TIMEOUT_S" "$(dirname "$0")/workload.sh" "$PORT"

sleep 1
kill -INT "$PERF_PID" >/dev/null 2>&1 || true
wait "$PERF_PID" >/dev/null 2>&1 || true
trap - EXIT

echo "perf data written to $PERF_DATA"
