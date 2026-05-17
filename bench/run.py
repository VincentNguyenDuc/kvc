#!/usr/bin/env python3
"""Host-side orchestration for the kvc benchmark.

Builds the bench image, pins the container to 2 CPUs with 1 GB RAM,
runs the full benchmark + perf pipeline, and writes results to:

  bench/output/<run-id>/
    meta.json        run metadata (label, timestamp, git commit, params)
    bench.json       throughput, latency histogram, hardware counters
    perf-report.txt  top functions by server CPU time
    flamegraph.svg   interactive CPU flamegraph

Usage:
  python bench/run.py [--label LABEL] [benchmark options]
  make bench BENCH_ARGS="--label v1 --requests 200000"
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent.resolve()
_REPO_ROOT  = _SCRIPT_DIR.parent
_OUTPUT_DIR = _SCRIPT_DIR / "output"
_IMAGE      = "kvc-bench"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _build() -> None:
    print(f"==> Building {_IMAGE} image...")
    subprocess.run(
        ["docker", "build", "--target", "bench", "-t", _IMAGE, str(_REPO_ROOT)],
        check=True,
    )


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--label",       default="",    help="human-readable label for this run")
    p.add_argument("--requests",    type=int,   default=100_000)
    p.add_argument("--connections", type=int,   default=1)
    p.add_argument("--warmup",      type=int,   default=1_000)
    p.add_argument("--key-space",   type=int,   default=10_000)
    p.add_argument("--value-size",  type=int,   default=64)
    p.add_argument("--set-ratio",   type=float, default=0.15)
    p.add_argument("--del-ratio",   type=float, default=0.05)
    p.add_argument("--no-build",    action="store_true", help="skip docker build (use cached image)")
    args = p.parse_args()

    if args.set_ratio + args.del_ratio > 1.0:
        sys.exit("error: --set-ratio + --del-ratio must be <= 1.0")

    ts         = datetime.now().strftime("%Y%m%d-%H%M%S")
    label_slug = args.label.replace(" ", "_") if args.label else "bench"
    run_id     = f"{label_slug}-{ts}"
    output_dir = _OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_build:
        _build()

    print(f"==> Run    : {run_id}")
    print(f"==> Output : bench/output/{run_id}/")
    print( "==> Env    : 2 CPUs (server=core0, client=core1), 1 GB RAM, loopback")
    print()

    cmd = [
        "docker", "run", "--rm",
        "--cpuset-cpus", "0-1",
        "--memory", "1g",
        "--memory-swap", "1g",
        "--cap-add=SYS_ADMIN",
        "--cap-add=PERFMON",
        "--security-opt", "seccomp=unconfined",
        "-v", f"{output_dir}:/output",
        _IMAGE,
        "python3", "bench/_entrypoint.py",
        "--output",     "/output",
        "--run-id",     run_id,
        "--label",      args.label or run_id,
        "--git-commit", _git_commit(),
        "--requests",   str(args.requests),
        "--connections",str(args.connections),
        "--warmup",     str(args.warmup),
        "--key-space",  str(args.key_space),
        "--value-size", str(args.value_size),
        "--set-ratio",  str(args.set_ratio),
        "--del-ratio",  str(args.del_ratio),
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)

    print(f"\n==> bench/output/{run_id}/")
    for f in sorted(output_dir.iterdir()):
        print(f"    {f.name:<22} {f.stat().st_size:>10,} B")


if __name__ == "__main__":
    main()
