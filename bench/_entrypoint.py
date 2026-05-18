#!/usr/bin/env python3
"""Container-side benchmark orchestration for kvc.

Runs the full pipeline inside Docker:
  1. Start server pinned to core 0 with perf stat + perf record
  2. Run async benchmark workers
  3. Stop server; flush perf data
  4. Write bench.json, perf-report.txt, meta.json to --output
"""

import argparse
import asyncio
import dataclasses
import json
import logging
import random
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import perf_orchestrator as po

sys.path.insert(0, "/workspace")

logging.basicConfig(
    level=logging.DEBUG, format="[%(asctime)s] %(levelname)s: %(message)s"
)


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


def _aggregate(
    results: list[_Result], elapsed: float, n_workers: int, label: str
) -> dict:
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
        ("min", 0),
        ("p50", 50),
        ("p95", 95),
        ("p99", 99),
        ("p999", 99.9),
        ("max", 100),
    ]
    timing_us = {k: round(_percentile(all_timings, p), 1) for k, p in pcts}

    return {
        "label": label,
        "workers": n_workers,
        "total": total,
        "errors": total_errors,
        "counts": all_counts,
        "duration_s": round(elapsed, 3),
        "throughput_per_s": round(total / elapsed) if elapsed > 0 else 0,
        "timing_us": timing_us,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--version", default="v1_baseline")
    p.add_argument("--output", required=True)
    p.add_argument("--run-id", default="")
    p.add_argument("--label", default="")
    p.add_argument("--git-commit", default="unknown")
    p.add_argument("--requests", type=int, default=100_000)
    p.add_argument("--connections", type=int, default=1)
    p.add_argument("--warmup", type=int, default=1_000)
    p.add_argument("--key-space", type=int, default=10_000)
    p.add_argument("--value-size", type=int, default=64)
    p.add_argument("--set-ratio", type=float, default=0.15)
    p.add_argument("--del-ratio", type=float, default=0.05)
    args = p.parse_args()

    output = Path(args.output)
    binary = Path(f"./build/{args.version}/kvc.o")
    if not binary.exists():
        sys.exit(
            f"error: binary not found: {binary} — was the image built with VERSION={args.version}?"
        )

    worker = _make_worker(
        "127.0.0.1",
        8080,
        args.key_space,
        args.value_size,
        args.set_ratio,
        args.del_ratio,
    )

    with po.Process(
        ["taskset", "-c", "0", f"./build/{args.version}/kvc.o", "8080", "16384"],
        perf=[po.PerfStat(), po.PerfRecord(output / "perf.data")],
        ready=_tcp_ready(port=8080),
    ) as server:
        results, elapsed = asyncio.run(
            _run(args.requests, args.warmup, args.connections, worker)
        )

    bench = _aggregate(results, elapsed, args.connections, args.label)
    server_report = server.report()
    if "perf_stat" in server_report:
        bench["perf"] = server_report["perf_stat"]

    perf_record_info = server_report.get("perf_record", {})
    if perf_record_info.get("stderr"):
        print(perf_record_info["stderr"], file=sys.stderr)

    (output / "bench.json").write_text(json.dumps(bench, indent=2))
    (output / "perf-report.txt").write_text(perf_record_info.get("report", ""))
    (output / "meta.json").write_text(
        json.dumps(
            {
                "run_id": args.run_id,
                "version": args.version,
                "label": args.label,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "git_commit": args.git_commit,
                "bench": {
                    "requests": args.requests,
                    "connections": args.connections,
                    "warmup": args.warmup,
                    "key_space": args.key_space,
                    "value_size": args.value_size,
                    "set_ratio": args.set_ratio,
                    "del_ratio": args.del_ratio,
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
