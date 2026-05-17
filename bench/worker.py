import asyncio
import random
import socket as _socket
import time

from perf_orchestrator import WorkerResult


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

    async def _worker(n_requests: int, n_warmup: int, result: WorkerResult) -> None:
        reader, writer = await asyncio.open_connection(host, port)
        sock = writer.transport.get_extra_info("socket")
        sock.setsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)

        for i in range(n_warmup):
            writer.write(f"SET k{i % key_space} {val}\n".encode())
            await writer.drain()
            await reader.readline()

        timings = result.timings_ns
        counts = result.counts

        for _ in range(n_requests):
            key = f"k{random.randrange(key_space)}"
            r = random.random()
            t0 = time.perf_counter_ns()
            try:
                if r < set_ratio:
                    writer.write(f"SET {key} {val}\n".encode())
                    counts["SET"] = counts.get("SET", 0) + 1
                elif r < set_ratio + del_ratio:
                    writer.write(f"DEL {key}\n".encode())
                    counts["DEL"] = counts.get("DEL", 0) + 1
                else:
                    writer.write(f"GET {key}\n".encode())
                    counts["GET"] = counts.get("GET", 0) + 1
                await writer.drain()
                await reader.readline()
            except Exception:
                result.errors += 1
            else:
                timings.append(time.perf_counter_ns() - t0)

        writer.close()
        await writer.wait_closed()

    return _worker
