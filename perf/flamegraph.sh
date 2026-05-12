#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <perf-data> <out-svg>" >&2
    exit 1
fi

PERF_DATA="$1"
OUT_SVG="$2"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$SCRIPT_DIR/tools"
FG_DIR="$TOOLS_DIR/FlameGraph"

if [[ ! -f "$PERF_DATA" ]]; then
    echo "perf data not found: $PERF_DATA" >&2
    exit 1
fi

if ! command -v perf >/dev/null 2>&1; then
    echo "perf is required but not installed" >&2
    exit 1
fi

mkdir -p "$TOOLS_DIR"
if [[ ! -d "$FG_DIR" ]]; then
    git clone --depth 1 https://github.com/brendangregg/FlameGraph.git "$FG_DIR"
fi

perf script -i "$PERF_DATA" | "$FG_DIR/stackcollapse-perf.pl" | "$FG_DIR/flamegraph.pl" > "$OUT_SVG"

echo "flamegraph written to $OUT_SVG"
