#!/usr/bin/env bash
set -euo pipefail

if ! command -v perf >/dev/null 2>&1; then
    echo "perf is not installed" >&2
    exit 1
fi

if perf record -e cpu-clock -o /tmp/kvc-perf-check.data -- true >/tmp/kvc-perf-check.log 2>&1; then
    rm -f /tmp/kvc-perf-check.data /tmp/kvc-perf-check.log
    echo "perf permissions are OK"
    exit 0
fi

cat /tmp/kvc-perf-check.log >&2 || true
rm -f /tmp/kvc-perf-check.data /tmp/kvc-perf-check.log

echo >&2
echo "perf is installed but not permitted in this container." >&2
echo "Start the container with perf capabilities, for example:" >&2
echo "  --cap-add=SYS_ADMIN --cap-add=PERFMON --security-opt seccomp=unconfined" >&2
echo "or lower kernel.perf_event_paranoid on the host." >&2
exit 1
