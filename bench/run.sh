#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_BASE="$SCRIPT_DIR/output"
IMAGE="kvc-bench"

# Defaults
LABEL=""
REQUESTS=100000
CONNECTIONS=1
WARMUP=1000
KEY_SPACE=10000
VALUE_SIZE=64
SET_RATIO=0.15
DEL_RATIO=0.05
NO_BUILD=0

usage() {
    cat <<'EOF'
Usage: bench/run.sh [OPTIONS]

Builds the bench image, runs the full benchmark + perf pipeline, and writes
results to bench/output/<run-id>/.

Options:
  --label STR         human-readable label for this run
  --requests N        total requests            (default: 100000)
  --connections N     concurrent connections    (default: 1)
  --warmup N          warmup requests           (default: 1000)
  --key-space N       key space size            (default: 10000)
  --value-size N      value size in bytes       (default: 64)
  --set-ratio F       fraction of SET ops       (default: 0.15)
  --del-ratio F       fraction of DEL ops       (default: 0.05)
  --no-build          skip docker build (use cached image)
  -h, --help          show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --label)       LABEL="$2";       shift 2 ;;
        --requests)    REQUESTS="$2";    shift 2 ;;
        --connections) CONNECTIONS="$2"; shift 2 ;;
        --warmup)      WARMUP="$2";      shift 2 ;;
        --key-space)   KEY_SPACE="$2";   shift 2 ;;
        --value-size)  VALUE_SIZE="$2";  shift 2 ;;
        --set-ratio)   SET_RATIO="$2";   shift 2 ;;
        --del-ratio)   DEL_RATIO="$2";   shift 2 ;;
        --no-build)    NO_BUILD=1;       shift   ;;
        -h|--help)     usage; exit 0 ;;
        *) echo "error: unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
done

if awk "BEGIN { exit !($SET_RATIO + $DEL_RATIO > 1.0) }"; then
    echo "error: --set-ratio + --del-ratio must be <= 1.0" >&2
    exit 1
fi

TS=$(date +%Y%m%d-%H%M%S)
LABEL_SLUG="${LABEL:+${LABEL// /_}}"
RUN_ID="${LABEL_SLUG:-bench}-${TS}"
OUTPUT_DIR="$OUTPUT_BASE/$RUN_ID"
GIT_COMMIT=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

mkdir -p "$OUTPUT_DIR"

if [[ "$NO_BUILD" -eq 0 ]]; then
    echo "==> Building $IMAGE image..."
    docker build --target bench -t "$IMAGE" "$REPO_ROOT"
fi

echo "==> Run    : $RUN_ID"
echo "==> Output : bench/output/$RUN_ID/"
echo "==> Env    : 2 CPUs (server=core0, client=core1), 1 GB RAM, loopback"
echo

docker run --rm \
    --cpuset-cpus 0-1 \
    --memory 1g \
    --memory-swap 1g \
    --cap-add=SYS_ADMIN \
    --cap-add=PERFMON \
    --security-opt seccomp=unconfined \
    -v "$OUTPUT_DIR:/output" \
    "$IMAGE" \
    python3 bench/_entrypoint.py \
        --output /output \
        --run-id "$RUN_ID" \
        --label "${LABEL:-$RUN_ID}" \
        --git-commit "$GIT_COMMIT" \
        --requests "$REQUESTS" \
        --connections "$CONNECTIONS" \
        --warmup "$WARMUP" \
        --key-space "$KEY_SPACE" \
        --value-size "$VALUE_SIZE" \
        --set-ratio "$SET_RATIO" \
        --del-ratio "$DEL_RATIO"

echo "==> Generating flamegraph..."
docker run --rm \
    -v "$OUTPUT_DIR:/output" \
    "$IMAGE" \
    bash -c "perf script -i /output/perf.data \
        | tools/FlameGraph/stackcollapse-perf.pl \
        | tools/FlameGraph/flamegraph.pl > /output/flamegraph.svg" \
    2>/dev/null || echo "    (flamegraph skipped — perf.data missing or empty)"

echo
echo "==> bench/output/$RUN_ID/"
for f in "$OUTPUT_DIR"/*; do
    [[ -f "$f" ]] || continue
    printf "    %-22s %10d B\n" "$(basename "$f")" "$(wc -c < "$f" | tr -d ' ')"
done
