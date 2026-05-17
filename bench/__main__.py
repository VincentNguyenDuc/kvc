"""Entry point for `python -m bench`."""
import json
import sys

import perf_orchestrator as po

from .worker import make_worker


def main() -> None:
    p = po.build_parser(description="kvc-bench: throughput and latency benchmark for kvc")
    p.add_argument("--key-space",  type=int,   default=10_000, help="number of unique keys")
    p.add_argument("--value-size", type=int,   default=64,     help="value size in bytes")
    p.add_argument("--set-ratio",  type=float, default=0.15,   help="fraction of SET ops")
    p.add_argument("--del-ratio",  type=float, default=0.05,   help="fraction of DEL ops")
    args = p.parse_args()

    if args.set_ratio + args.del_ratio > 1.0:
        print("error: --set-ratio + --del-ratio must be <= 1.0", file=sys.stderr)
        sys.exit(1)

    worker = make_worker(args.key_space, args.value_size, args.set_ratio, args.del_ratio)
    result = po.run(args, worker)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        po.print_result(result)


if __name__ == "__main__":
    main()
