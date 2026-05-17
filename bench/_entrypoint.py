#!/usr/bin/env python3
"""Container-side orchestration: server, perf, benchmark, and output pipeline.

Called by bench/run.py inside the Docker container. Not intended for direct use.

Always runs the full pipeline:
  1. Start server pinned to core 0
  2. Start perf record (cpu-clock + dwarf call-graph)
  3. Run benchmark with perf stat attached for hardware counters
  4. Stop perf record; generate perf-report.txt and flamegraph.svg
  5. Write bench.json, perf-report.txt, flamegraph.svg, perf.data, meta.json to --output
"""
import argparse
import json
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/workspace")
import perf_orchestrator as po
from bench.worker import make_worker

_FG_COLLAPSE = Path("tools/FlameGraph/stackcollapse-perf.pl")
_FG_RENDER   = Path("tools/FlameGraph/flamegraph.pl")


def _wait_for_server(host: str = "127.0.0.1", port: int = 8080, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            socket.create_connection((host, port), timeout=0.1).close()
            return
        except OSError:
            time.sleep(0.1)
    sys.exit(f"error: server did not start on {host}:{port} within {timeout}s")


def _stop(proc: subprocess.Popen, sig: signal.Signals = signal.SIGTERM, wait: float = 5.0) -> None:
    try:
        proc.send_signal(sig)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _perf_report(perf_data: Path) -> str:
    if not perf_data.exists() or perf_data.stat().st_size == 0:
        return "(perf.data missing or empty — perf record may have failed)"
    r = subprocess.run(
        ["perf", "report", "-i", str(perf_data), "--stdio", "--no-children", "-g", "none"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return f"(perf report failed)\n{r.stderr.strip()}"
    lines = [l for l in r.stdout.splitlines() if l and not l.startswith("#")]
    return "\n".join(lines) or f"(no samples)\n{r.stderr.strip()}"


def _flamegraph(perf_data: Path) -> bytes | None:
    if not (_FG_COLLAPSE.is_file() and _FG_RENDER.is_file()):
        print("warning: FlameGraph scripts not found, skipping flamegraph", file=sys.stderr)
        return None
    s = subprocess.run(["perf", "script", "-i", str(perf_data)], capture_output=True)
    c = subprocess.run(["perl", str(_FG_COLLAPSE)], input=s.stdout, capture_output=True)
    r = subprocess.run(["perl", str(_FG_RENDER)],   input=c.stdout, capture_output=True)
    return r.stdout if r.returncode == 0 and r.stdout else None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output",      required=True)
    p.add_argument("--run-id",      default="")
    p.add_argument("--label",       default="")
    p.add_argument("--git-commit",  default="unknown")
    p.add_argument("--requests",    type=int,   default=100_000)
    p.add_argument("--connections", type=int,   default=1)
    p.add_argument("--warmup",      type=int,   default=1_000)
    p.add_argument("--key-space",   type=int,   default=10_000)
    p.add_argument("--value-size",  type=int,   default=64)
    p.add_argument("--set-ratio",   type=float, default=0.15)
    p.add_argument("--del-ratio",   type=float, default=0.05)
    args = p.parse_args()

    output = Path(args.output)
    perf_data = output / "perf.data"

    # ------------------------------------------------------------------
    # 1. Server — core 0
    # ------------------------------------------------------------------
    server = subprocess.Popen(
        ["taskset", "-c", "0", "./build/kvc.o", "8080", "16384"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_server()

    perf_record: subprocess.Popen | None = None
    bench_result: dict = {}

    try:
        # ------------------------------------------------------------------
        # 2. perf record
        # ------------------------------------------------------------------
        perf_record = subprocess.Popen(
            [
                "perf", "record",
                "-p", str(server.pid),
                "-e", "cpu-clock",
                "--call-graph", "dwarf",
                "-F", "99",
                "-o", str(perf_data),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # ------------------------------------------------------------------
        # 3. Benchmark
        # ------------------------------------------------------------------
        import argparse as _ap
        worker = make_worker(args.key_space, args.value_size, args.set_ratio, args.del_ratio)
        bench_result = po.run(_ap.Namespace(
            host="127.0.0.1",
            port=8080,
            requests=args.requests,
            connections=args.connections,
            warmup=args.warmup,
            label=args.label,
            perf_pid=server.pid,
        ), worker)
        po.print_result(bench_result)

    finally:
        if perf_record is not None:
            _stop(perf_record, signal.SIGINT)
            perf_err = perf_record.stderr.read().decode(errors="replace").strip()
            if perf_err:
                print(f"[perf record] {perf_err}", file=sys.stderr)
        _stop(server)

    # ------------------------------------------------------------------
    # 4. Post-processing
    # ------------------------------------------------------------------
    print("\n==> Generating perf report...")
    report = _perf_report(perf_data)

    print("==> Generating flamegraph...")
    fg = _flamegraph(perf_data)

    # ------------------------------------------------------------------
    # 5. Write output files
    # ------------------------------------------------------------------
    (output / "bench.json").write_text(json.dumps(bench_result, indent=2))
    (output / "perf-report.txt").write_text(report)
    if fg:
        (output / "flamegraph.svg").write_bytes(fg)

    (output / "meta.json").write_text(json.dumps({
        "run_id":     args.run_id,
        "label":      args.label,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "git_commit": args.git_commit,
        "bench": {
            "requests":    args.requests,
            "connections": args.connections,
            "warmup":      args.warmup,
            "key_space":   args.key_space,
            "value_size":  args.value_size,
            "set_ratio":   args.set_ratio,
            "del_ratio":   args.del_ratio,
        },
    }, indent=2))


if __name__ == "__main__":
    main()
