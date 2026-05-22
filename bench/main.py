#!/usr/bin/env python3
"""kvc benchmark orchestration — build, run, profile, report.

Full pipeline:
  1. (optional) Build the kvc binary with make
  2. Pin this process to core 1; start the kvc server pinned to core 0
  3. Run async benchmark workers with perf stat + perf record
  4. Stop server; flush perf data; write bench.json
  5. Generate flamegraph SVG

Usage (native — output dir auto-generated under bench/output/):
    python3 bench/main.py [OPTIONS]

Usage (Docker — caller mounts output dir and skips build):
    python3 bench/main.py --output /output --no-build [OPTIONS]
"""

import argparse
import asyncio
import dataclasses
import json
import logging
import os
import platform
import random
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import perf_orchestrator as po

sys.path.insert(0, "/workspace")

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

logging.basicConfig(
    level=logging.DEBUG, format="[%(asctime)s] %(levelname)s: %(message)s"
)


# ---------------------------------------------------------------------------
# Infrastructure / build helpers
# ---------------------------------------------------------------------------

def _collect_infra() -> dict:
    info: dict = {
        "hostname":  platform.node(),
        "os":        f"{platform.system()} {platform.release()}",
        "arch":      platform.machine(),
        "cpu_count": os.cpu_count(),
    }
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    info["cpu_model"] = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    return info


def _get_git_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def _build(version: str) -> None:
    print(f"==> Building {version} (native)...")
    subprocess.run(
        [
            "make", "-C", str(_REPO_ROOT), f"VERSION={version}",
            "CFLAGS=-O2 -g -Wall -Wextra -Wpedantic -fno-omit-frame-pointer",
        ],
        check=True,
    )


def _generate_flamegraph(output: Path) -> None:
    perf_data = output / "perf.data"
    if not perf_data.exists() or perf_data.stat().st_size == 0:
        print("    (skipped — perf.data missing or empty)")
        return
    fg_dir = _REPO_ROOT / "tools" / "FlameGraph"
    ksyms = ["--kallsyms", "/kallsyms"] if Path("/kallsyms").exists() else []
    try:
        p1 = subprocess.run(
            ["perf", "script"] + ksyms + ["-i", str(perf_data)],
            capture_output=True,
        )
        p2 = subprocess.run(
            ["perl", str(fg_dir / "stackcollapse-perf.pl")],
            input=p1.stdout, capture_output=True,
        )
        p3 = subprocess.run(
            ["perl", str(fg_dir / "flamegraph.pl")],
            input=p2.stdout, capture_output=True,
        )
        (output / "flamegraph.svg").write_bytes(p3.stdout)
    except Exception as e:
        print(f"    (skipped — {e})")


# ---------------------------------------------------------------------------
# Benchmark worker
# ---------------------------------------------------------------------------

def _tcp_ready(
    host: str = "127.0.0.1", port: int = 8080, timeout: float = 5.0
) -> po.ReadyFn:
    def _check() -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                socket.create_connection((host, port), timeout=0.1).close()
                return
            except OSError:
                time.sleep(0.05)
        raise TimeoutError(
            f"process did not become ready on {host}:{port} within {timeout}s"
        )
    return _check


@dataclasses.dataclass
class _Result:
    timings_ns: list[int] = dataclasses.field(default_factory=list)
    counts: dict[str, int] = dataclasses.field(default_factory=dict)
    errors: int = 0


def _make_worker(
    host: str,
    port: int,
    key_space: int,
    value_size: int,
    set_ratio: float,
    del_ratio: float,
):
    val = "x" * value_size

    async def _worker(n_requests: int, n_warmup: int, result: _Result) -> None:
        reader, writer = await asyncio.open_connection(host, port)
        sock = writer.transport.get_extra_info("socket")
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        for i in range(n_warmup):
            writer.write(f"SET k{i % key_space} {val}\n".encode())
            await writer.drain()
            await reader.readline()

        for _ in range(n_requests):
            key = f"k{random.randrange(key_space)}"
            r = random.random()
            t0 = time.perf_counter_ns()
            try:
                if r < set_ratio:
                    writer.write(f"SET {key} {val}\n".encode())
                    result.counts["SET"] = result.counts.get("SET", 0) + 1
                elif r < set_ratio + del_ratio:
                    writer.write(f"DEL {key}\n".encode())
                    result.counts["DEL"] = result.counts.get("DEL", 0) + 1
                else:
                    writer.write(f"GET {key}\n".encode())
                    result.counts["GET"] = result.counts.get("GET", 0) + 1
                await writer.drain()
                await reader.readline()
            except Exception:
                result.errors += 1
            else:
                result.timings_ns.append(time.perf_counter_ns() - t0)

        writer.close()
        await writer.wait_closed()

    return _worker


async def _run(
    n_requests: int, n_warmup: int, n_workers: int, worker_fn
) -> tuple[list[_Result], float]:
    results = [_Result() for _ in range(n_workers)]
    n_per = n_requests // n_workers
    t0 = time.monotonic()
    await asyncio.gather(*(worker_fn(n_per, n_warmup, r) for r in results))
    return results, time.monotonic() - t0


def _percentile(sorted_ns: list[int], p: float) -> float:
    if not sorted_ns:
        return 0.0
    idx = min(int(len(sorted_ns) * p / 100), len(sorted_ns) - 1)
    return sorted_ns[idx] / 1_000  # ns -> µs


def _aggregate(results: list[_Result], elapsed: float, n_workers: int) -> dict:
    all_timings: list[int] = []
    all_counts: dict[str, int] = {}
    total_errors = 0
    for r in results:
        all_timings.extend(r.timings_ns)
        for k, v in r.counts.items():
            all_counts[k] = all_counts.get(k, 0) + v
        total_errors += r.errors

    all_timings.sort()
    total = len(all_timings)
    pcts = [
        ("min", 0), ("p50", 50), ("p95", 95),
        ("p99", 99), ("p999", 99.9), ("max", 100),
    ]
    timing_us = {k: round(_percentile(all_timings, p), 1) for k, p in pcts}

    return {
        "workers":          n_workers,
        "total":            total,
        "errors":           total_errors,
        "counts":           all_counts,
        "duration_s":       round(elapsed, 3),
        "throughput_per_s": round(total / elapsed) if elapsed > 0 else 0,
        "timing_us":        timing_us,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version",     default="v1_baseline", help="implementation version")
    p.add_argument("--output",      default=None,  help="output dir (auto-generated under bench/output/ if omitted)")
    p.add_argument("--run-id",      default="",    help="run identifier (auto-generated if omitted)")
    p.add_argument("--label",       default="",    help="human-readable label")
    p.add_argument("--git-commit",  default="",    help="git commit hash (auto-detected if omitted)")
    p.add_argument("--env",         default="native", help="execution environment tag, e.g. native, docker, Azure-Standard_D2s_v3")
    p.add_argument("--no-build",    action="store_true", help="skip make (binary must already exist)")
    p.add_argument("--requests",    type=int,   default=100_000)
    p.add_argument("--connections", type=int,   default=1)
    p.add_argument("--warmup",      type=int,   default=1_000)
    p.add_argument("--key-space",   type=int,   default=10_000)
    p.add_argument("--value-size",  type=int,   default=64)
    p.add_argument("--set-ratio",   type=float, default=0.15)
    p.add_argument("--del-ratio",   type=float, default=0.05)
    args = p.parse_args()

    if args.set_ratio + args.del_ratio > 1.0:
        sys.exit("error: --set-ratio + --del-ratio must be <= 1.0")

    ts = datetime.now(timezone.utc)
    run_id     = args.run_id    or f"bench-{ts.strftime('%Y%m%d-%H%M%S')}"
    label      = args.label     or run_id
    git_commit = args.git_commit or _get_git_commit()

    output = Path(args.output) if args.output else (
        _SCRIPT_DIR / "output" / args.version / run_id
    )
    output.mkdir(parents=True, exist_ok=True)

    if not args.no_build:
        _build(args.version)

    # Pin benchmark client to core 1 (Linux only; silently skipped elsewhere)
    try:
        os.sched_setaffinity(0, {1})  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    binary = _REPO_ROOT / "build" / args.version / "kvc.o"
    if not binary.exists():
        sys.exit(f"error: binary not found: {binary} — build with VERSION={args.version}")

    print(f"==> Version : {args.version}")
    print(f"==> Run     : {run_id}")
    print(f"==> Output  : {output}/")
    print(f"==> Env     : {args.env} — server pinned to core 0, client pinned to core 1")
    print()

    worker = _make_worker(
        "127.0.0.1", 8080,
        args.key_space, args.value_size, args.set_ratio, args.del_ratio,
    )

    with po.Process(
        ["taskset", "-c", "0", str(binary), "8080", "16384"],
        perf=[po.PerfStat(), po.PerfRecord(output / "perf.data")],
        ready=_tcp_ready(port=8080),
    ) as server:
        results, elapsed = asyncio.run(
            _run(args.requests, args.warmup, args.connections, worker)
        )

    bench = _aggregate(results, elapsed, args.connections)
    server_report = server.report()
    perf_stat_data = server_report.get("perf_stat", {})

    perf_record_info = server_report.get("perf_record", {})
    if perf_record_info.get("stderr"):
        print(perf_record_info["stderr"], file=sys.stderr)

    result: dict = {
        "run_id":     run_id,
        "version":    args.version,
        "label":      label,
        "timestamp":  ts.isoformat(),
        "git_commit": git_commit,
        "env":        args.env,
        "infra":      _collect_infra(),
        "config": {
            "requests":    args.requests,
            "connections": args.connections,
            "warmup":      args.warmup,
            "key_space":   args.key_space,
            "value_size":  args.value_size,
            "set_ratio":   args.set_ratio,
            "del_ratio":   args.del_ratio,
        },
        "workers":          bench["workers"],
        "total":            bench["total"],
        "errors":           bench["errors"],
        "counts":           bench["counts"],
        "duration_s":       bench["duration_s"],
        "throughput_per_s": bench["throughput_per_s"],
        "timing_us":        bench["timing_us"],
    }
    if perf_stat_data:
        result["perf"] = perf_stat_data
    perf_report_text = perf_record_info.get("report", "")
    if perf_report_text:
        result["perf_report"] = perf_report_text

    (output / "bench.json").write_text(json.dumps(result, indent=2))

    print("==> Generating flamegraph...")
    _generate_flamegraph(output)

    print()
    print(f"==> {output}/")
    for f in sorted(output.iterdir()):
        if f.is_file():
            print(f"    {f.name:<22} {f.stat().st_size:>10,} B")


if __name__ == "__main__":
    main()
