#!/usr/bin/env bash
# bench/docker.sh — Docker benchmark runner for kvc.
#
# Builds the kvc-bench image, runs the full perf pipeline inside a container
# (2 CPUs, 1 GB RAM, loopback), and writes results to bench/output/<version>/<run-id>/.
#
# Requires: docker
# Usage: bench/docker.sh [OPTIONS]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_BASE="$SCRIPT_DIR/output"
IMAGE="kvc-bench"

# Defaults
VERSION="v1_baseline"
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
Usage: bench/docker.sh [OPTIONS]

Builds the kvc-bench Docker image, runs the benchmark + perf pipeline inside a
container, and writes results to bench/output/<version>/<run-id>/.

Options:
  --version STR       implementation version    (default: v1_baseline)
  --label STR         human-readable label for this run
  --requests N        total requests            (default: 100000)
  --connections N     concurrent connections    (default: 1)
  --warmup N          warmup requests           (default: 1000)
  --key-space N       key space size            (default: 10000)
  --value-size N      value size in bytes       (default: 64)
  --set-ratio F       fraction of SET ops       (default: 0.15)
  --del-ratio F       fraction of DEL ops       (default: 0.05)
  --no-build          skip docker build (use existing image)
  -h, --help          show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)     VERSION="$2";     shift 2 ;;
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
OUTPUT_DIR="$OUTPUT_BASE/$VERSION/$RUN_ID"
GIT_COMMIT=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

mkdir -p "$OUTPUT_DIR"

ENTRYPOINT_ARGS=(
    --version    "$VERSION"
    --run-id     "$RUN_ID"
    --label      "${LABEL:-$RUN_ID}"
    --git-commit "$GIT_COMMIT"
    --env        "docker"
    --no-build
    --requests   "$REQUESTS"
    --connections "$CONNECTIONS"
    --warmup     "$WARMUP"
    --key-space  "$KEY_SPACE"
    --value-size "$VALUE_SIZE"
    --set-ratio  "$SET_RATIO"
    --del-ratio  "$DEL_RATIO"
)

# Mount /proc/kallsyms outside /proc so perf inside the container can
# resolve kernel symbols (Docker blocks bind-mounts into container /proc).
KALLSYMS_MOUNT=()
[[ -f /proc/kallsyms ]] && KALLSYMS_MOUNT=(-v /proc/kallsyms:/kallsyms:ro)

if [[ "$NO_BUILD" -eq 0 ]]; then
    echo "==> Building $IMAGE image..."
    docker build --target bench -t "$IMAGE" "$REPO_ROOT"
fi

docker run --rm \
    --cpuset-cpus 0-1 \
    --memory 1g \
    --memory-swap 1g \
    --cap-add=SYS_ADMIN \
    --cap-add=PERFMON \
    --security-opt seccomp=unconfined \
    -v "$OUTPUT_DIR:/output" \
    "${KALLSYMS_MOUNT[@]+"${KALLSYMS_MOUNT[@]}"}" \
    "$IMAGE" \
    python3 bench/main.py --output /output "${ENTRYPOINT_ARGS[@]}"
