#!/usr/bin/env python3
"""Container-side orchestration: server, perf, benchmark, and output pipeline.

Called by bench/run.py inside the Docker container. Not intended for direct use.

Always runs the full pipeline:
  1. Start server pinned to core 0 with perf stat + perf record attached
  2. Run benchmark workers concurrently
  3. Stop server; flush perf data
"""

import argparse
import asyncio
import random
import socket
import sys
import time
from pathlib import Path

import perf_orchestrator as po

sys.path.insert(0, "/workspace")


def tcp_ready(
    host: str = "127.0.0.1", port: int = 8080, timeout: float = 5.0
) -> po.ReadyFn:
    """Return a readiness check that polls until a TCP connection succeeds."""

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


def make_worker(
    host: str,
    port: int,
    key_space: int,
    value_size: int,
    set_ratio: float,
    del_ratio: float,
):
    """Return an async worker closed over all KVC connection and workload parameters."""
    val = "x" * value_size

    async def _worker(n_requests: int, n_warmup: int) -> None:
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
                elif r < set_ratio + del_ratio:
                    writer.write(f"DEL {key}\n".encode())
                else:
                    writer.write(f"GET {key}\n".encode())
                await writer.drain()
                await reader.readline()
            except Exception:
                print("Error during request:", file=sys.stderr)
            else:
                print(time.perf_counter_ns() - t0)

        writer.close()
        await writer.wait_closed()

    return _worker


async def _run(n_requests: int, n_warmup: int, n_workers: int, worker_fn) -> float:
    n_per = n_requests // n_workers
    t0 = time.monotonic()
    await asyncio.gather(*(worker_fn(n_per, n_warmup) for _ in range(n_workers)))
    return time.monotonic() - t0


def main() -> None:
    p = argparse.ArgumentParser()
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

    worker = make_worker(
        "127.0.0.1",
        8080,
        args.key_space,
        args.value_size,
        args.set_ratio,
        args.del_ratio,
    )

    with po.Process(
        ["taskset", "-c", "0", "./build/kvc.o", "8080", "16384"],
        perf_stat=True,
        perf_record=True,
        record_output=output / "perf.data",
        ready=tcp_ready(port=8080),
    ) as server:
        result = asyncio.run(_run(args.requests, args.warmup, args.connections, worker))

    server_report = server.report()
    print(server_report)
    print(result)


if __name__ == "__main__":
    main()
