import asyncio
import random
import socket as _socket
import time

from pyperf import WorkerResult


def make_worker(key_space: int, value_size: int, set_ratio: float, del_ratio: float):
    """Return an async worker coroutine closed over KVC-specific parameters."""
    val = "x" * value_size

    async def _worker(
        host: str,
        port: int,
        n_requests: int,
        n_warmup: int,
        result: WorkerResult,
    ) -> None:
        reader, writer = await asyncio.open_connection(host, port)
        sock = writer.transport.get_extra_info("socket")
        sock.setsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)

        for i in range(n_warmup):
            writer.write(f"SET k{i % key_space} {val}\n".encode())
            await writer.drain()
            await reader.readline()

        latencies = result.latencies_ns
        op_counts = result.op_counts

        for _ in range(n_requests):
            key = f"k{random.randrange(key_space)}"
            r = random.random()
            t0 = time.perf_counter_ns()
            try:
                if r < set_ratio:
                    writer.write(f"SET {key} {val}\n".encode())
                    op_counts["SET"] = op_counts.get("SET", 0) + 1
                elif r < set_ratio + del_ratio:
                    writer.write(f"DEL {key}\n".encode())
                    op_counts["DEL"] = op_counts.get("DEL", 0) + 1
                else:
                    writer.write(f"GET {key}\n".encode())
                    op_counts["GET"] = op_counts.get("GET", 0) + 1
                await writer.drain()
                await reader.readline()
            except Exception:
                result.errors += 1
            else:
                latencies.append(time.perf_counter_ns() - t0)

        writer.close()
        await writer.wait_closed()

    return _worker
