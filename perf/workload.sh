#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8080}"
NC_OPTS=(-N -w 1)

# Warm up and mixed workload for GET/SET/DEL profile samples.
for i in $(seq 1 2000); do
    printf 'SET key%s value%s\n' "$i" "$i"
done | nc "${NC_OPTS[@]}" 127.0.0.1 "$PORT" >/dev/null

for _ in $(seq 1 10); do
    {
        for i in $(seq 1 2000); do
            printf 'GET key%s\n' "$i"
        done
        for i in $(seq 1 1000); do
            printf 'DEL key%s\n' "$i"
        done
        for i in $(seq 1 1000); do
            printf 'SET key%s value%s\n' "$i" "$i"
        done
    } | nc "${NC_OPTS[@]}" 127.0.0.1 "$PORT" >/dev/null
done
