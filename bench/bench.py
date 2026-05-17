#!/usr/bin/env python3
"""kvc-bench: throughput and latency benchmark for the kvc key-value store."""

import argparse
import json
import random
import re
import signal
import socket
import subprocess
import sys
import time
from threading import Thread


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class KvcConn:
    def __init__(self, host: str, port: int):
        self._sock = socket.create_connection((host, port))
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._buf = b""

    def _roundtrip(self, cmd: bytes) -> bytes:
        self._sock.sendall(cmd)
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("server closed connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line

    def set(self, key: str, value: str) -> bytes:
        return self._roundtrip(f"SET {key} {value}\n".encode())

    def get(self, key: str) -> bytes:
        return self._roundtrip(f"GET {key}\n".encode())

    def delete(self, key: str) -> bytes:
        return self._roundtrip(f"DEL {key}\n".encode())

    def close(self):
        self._sock.close()


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class WorkerResult:
    __slots__ = ("latencies_ns", "op_counts", "errors")

    def __init__(self):
        self.latencies_ns: list[int] = []
        self.op_counts: dict[str, int] = {"GET": 0, "SET": 0, "DEL": 0}
        self.errors: int = 0


def _value(size: int) -> str:
    return "x" * size


def _worker(
    host: str,
    port: int,
    n_requests: int,
    n_warmup: int,
    key_space: int,
    value_size: int,
    set_ratio: float,
    del_ratio: float,
    result: WorkerResult,
) -> None:
    conn = KvcConn(host, port)
    val = _value(value_size)

    for i in range(n_warmup):
        conn.set(f"k{i % key_space}", val)

    latencies = result.latencies_ns
    op_counts = result.op_counts

    for _ in range(n_requests):
        key = f"k{random.randrange(key_space)}"
        r = random.random()
        t0 = time.perf_counter_ns()
        try:
            if r < set_ratio:
                conn.set(key, val)
                op_counts["SET"] += 1
            elif r < set_ratio + del_ratio:
                conn.delete(key)
                op_counts["DEL"] += 1
            else:
                conn.get(key)
                op_counts["GET"] += 1
        except Exception:
            result.errors += 1
        else:
            latencies.append(time.perf_counter_ns() - t0)

    conn.close()


# ---------------------------------------------------------------------------
# perf stat
# ---------------------------------------------------------------------------

# Events requested from perf stat. Some may be unavailable on a given CPU or
# inside a VM — perf will report those as <not supported> which we skip.
_PERF_EVENTS = ",".join([
    "cache-references",
    "cache-misses",
    "instructions",
    "cycles",
    "branch-misses",
    "branch-instructions",
    "L1-dcache-load-misses",
    "dTLB-load-misses",
])

# Matches a counter line from `perf stat` text output, e.g.:
#      1,234,567      cache-references          # 2.29% of all cache refs
#            123      L1-dcache-load-misses:u
_STAT_LINE_RE = re.compile(
    r"^\s+([\d,]+)\s+([a-zA-Z0-9_\-]+)(?::[a-zA-Z]+)?"
)


class PerfStat:
    """
    Attaches `perf stat` to the server process and collects hardware
    performance counters for the duration of the benchmark.

    Requires the `perf` tool and sufficient privileges:
      - CAP_PERFMON (Linux 5.8+), or
      - CAP_SYS_ADMIN, or
      - kernel.perf_event_paranoid <= 1
    """

    def __init__(self, pid: int):
        self._pid = pid
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        cmd = ["perf", "stat", "-p", str(self._pid), "-e", _PERF_EVENTS]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            print("warning: perf not found — skipping hardware counters", file=sys.stderr)

    def stop(self) -> dict:
        """Send SIGINT to perf stat, wait for it, and return parsed counters."""
        if self._proc is None:
            return {}
        self._proc.send_signal(signal.SIGINT)
        try:
            _, stderr = self._proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            _, stderr = self._proc.communicate()
        return _parse_perf_stat(stderr.decode(errors="replace"))


def _parse_perf_stat(output: str) -> dict:
    """Parse `perf stat` text output into counters and derived metrics."""
    counters: dict[str, int] = {}
    for line in output.splitlines():
        m = _STAT_LINE_RE.match(line)
        if not m:
            continue
        raw_val, event = m.group(1), m.group(2)
        try:
            counters[event] = int(raw_val.replace(",", ""))
        except ValueError:
            pass

    if not counters:
        return {}

    cache_refs  = counters.get("cache-references", 0)
    cache_miss  = counters.get("cache-misses", 0)
    instrs      = counters.get("instructions", 0)
    cycles      = counters.get("cycles", 0)
    br_miss     = counters.get("branch-misses", 0)
    br_total    = counters.get("branch-instructions", 0)

    derived: dict[str, float] = {}
    if cache_refs > 0:
        derived["cache_miss_rate_pct"] = round(cache_miss / cache_refs * 100, 2)
    if cycles > 0:
        derived["ipc"] = round(instrs / cycles, 3)
        derived["cpi"] = round(cycles / instrs, 3) if instrs else 0.0
    if br_total > 0:
        derived["branch_miss_rate_pct"] = round(br_miss / br_total * 100, 2)

    return {"counters": counters, "derived": derived}


# ---------------------------------------------------------------------------
# Percentile helper
# ---------------------------------------------------------------------------

def _pct(sorted_ns: list[int], p: float) -> float:
    if not sorted_ns:
        return 0.0
    idx = min(int(len(sorted_ns) * p / 100), len(sorted_ns) - 1)
    return sorted_ns[idx] / 1_000  # ns -> us


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> dict:
    perf: PerfStat | None = None
    if args.perf_pid:
        perf = PerfStat(args.perf_pid)
        perf.start()

    results = [WorkerResult() for _ in range(args.connections)]
    threads = [
        Thread(
            target=_worker,
            args=(
                args.host,
                args.port,
                args.requests // args.connections,
                args.warmup // args.connections,
                args.key_space,
                args.value_size,
                args.set_ratio,
                args.del_ratio,
                results[i],
            ),
            daemon=True,
        )
        for i in range(args.connections)
    ]

    t_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t_start

    perf_data = perf.stop() if perf else None

    all_ns: list[int] = []
    op_counts = {"GET": 0, "SET": 0, "DEL": 0}
    total_errors = 0
    for r in results:
        all_ns.extend(r.latencies_ns)
        for op in op_counts:
            op_counts[op] += r.op_counts[op]
        total_errors += r.errors

    all_ns.sort()
    total_ops = sum(op_counts.values())

    result: dict = {
        "label": args.label,
        "connections": args.connections,
        "requests": args.requests,
        "key_space": args.key_space,
        "value_size": args.value_size,
        "set_ratio": args.set_ratio,
        "del_ratio": args.del_ratio,
        "duration_s": round(elapsed, 3),
        "total_ops": total_ops,
        "throughput_ops_per_s": round(total_ops / elapsed) if elapsed > 0 else 0,
        "errors": total_errors,
        "op_counts": op_counts,
        "latency_us": {
            "min":  round(_pct(all_ns,   0), 2),
            "p50":  round(_pct(all_ns,  50), 2),
            "p95":  round(_pct(all_ns,  95), 2),
            "p99":  round(_pct(all_ns,  99), 2),
            "p999": round(_pct(all_ns,  99.9), 2),
            "max":  round(_pct(all_ns, 100), 2),
        },
    }
    if perf_data:
        result["perf"] = perf_data
    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_result(r: dict) -> None:
    if r["label"]:
        print(f"\n{'='*60}")
        print(f"  {r['label']}")
        print(f"{'='*60}")

    lat = r["latency_us"]
    mix = r["op_counts"]
    print(f"connections : {r['connections']}")
    print(f"requests    : {r['total_ops']:,}  (errors: {r['errors']})")
    print(f"op mix      : GET={mix['GET']:,}  SET={mix['SET']:,}  DEL={mix['DEL']:,}")
    print(f"duration    : {r['duration_s']} s")
    print(f"throughput  : {r['throughput_ops_per_s']:,} ops/sec")
    print(f"latency us  : min={lat['min']}  p50={lat['p50']}  "
          f"p95={lat['p95']}  p99={lat['p99']}  "
          f"p999={lat['p999']}  max={lat['max']}")

    if "perf" in r:
        _print_perf(r["perf"])


def _print_perf(p: dict) -> None:
    c = p.get("counters", {})
    d = p.get("derived", {})

    print()
    print("--- hardware counters (server process) ---")

    if not c:
        print("  (no data — perf may require CAP_PERFMON or perf_event_paranoid <= 1)")
        return

    rows = [
        ("cache-references",      "cache refs"),
        ("cache-misses",          "cache misses"),
        ("L1-dcache-load-misses", "L1d load misses"),
        ("dTLB-load-misses",      "dTLB load misses"),
        ("instructions",          "instructions"),
        ("cycles",                "cycles"),
        ("branch-instructions",   "branches"),
        ("branch-misses",         "branch misses"),
    ]
    for key, label in rows:
        val = c.get(key)
        if val is not None:
            print(f"  {label:<24}: {val:>16,}")

    if d:
        print()
        if "cache_miss_rate_pct" in d:
            print(f"  cache miss rate         : {d['cache_miss_rate_pct']}%")
        if "ipc" in d:
            print(f"  IPC                     : {d['ipc']}")
        if "cpi" in d:
            print(f"  CPI                     : {d['cpi']}")
        if "branch_miss_rate_pct" in d:
            print(f"  branch miss rate        : {d['branch_miss_rate_pct']}%")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="kvc-bench: throughput and latency benchmark",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--host",        default="127.0.0.1",    help="server host")
    p.add_argument("--port",        type=int, default=8080,  help="server port")
    p.add_argument("--requests",    type=int, default=100_000, help="total requests")
    p.add_argument("--connections", type=int, default=1,     help="concurrent connections")
    p.add_argument("--warmup",      type=int, default=1_000, help="warmup requests (excluded from metrics)")
    p.add_argument("--key-space",   type=int, default=10_000, help="number of unique keys")
    p.add_argument("--value-size",  type=int, default=64,    help="value size in bytes")
    p.add_argument("--set-ratio",   type=float, default=0.15, help="fraction of SET ops")
    p.add_argument("--del-ratio",   type=float, default=0.05, help="fraction of DEL ops")
    p.add_argument("--label",       default="",              help="label printed in the report")
    p.add_argument("--json",        action="store_true",     help="output JSON instead of text")
    p.add_argument(
        "--perf-pid",
        type=int,
        default=0,
        metavar="PID",
        help="attach perf stat to this server PID to collect hardware counters",
    )
    args = p.parse_args()

    if args.set_ratio + args.del_ratio > 1.0:
        print("error: --set-ratio + --del-ratio must be <= 1.0", file=sys.stderr)
        sys.exit(1)

    result = run(args)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_result(result)


if __name__ == "__main__":
    main()
