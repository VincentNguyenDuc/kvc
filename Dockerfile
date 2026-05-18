
# Base stage with common dependencies for both development and runtime
FROM debian:bookworm-slim AS base

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
    clang-format \
        make \
        gdb \
        strace \
        netcat-openbsd \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Dev stage with extra tools for development and debugging
FROM base AS dev
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        git \
        linux-perf \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://starship.rs/install.sh | sh -s -- -y \
   && echo 'eval "$(starship init bash)"' >> /etc/bash.bashrc

CMD ["bash"]

# Run stage with only the necessary files to run the application
FROM base AS run
ARG VERSION=v1_baseline
COPY . /workspace
RUN make VERSION=${VERSION}
EXPOSE 8080
CMD ["sh", "-c", "exec ./build/${VERSION}/kvc.o 8080 1024"]

# Bench stage: server binaries (all versions) + Python3 benchmark client + perf + taskset
#
# Built with -fno-omit-frame-pointer so perf can unwind call stacks via frame
# pointers (--call-graph fp) without the overhead of DWARF unwinding.
FROM base AS bench
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        util-linux \
        linux-perf \
        perl \
        libc6-dbg \
    && rm -rf /var/lib/apt/lists/*
COPY . /workspace
RUN pip3 install --break-system-packages /workspace/tools/perf-orchestrator
RUN for v in src/*/; do \
        make VERSION="$(basename "$v")" CFLAGS="-O2 -g -Wall -Wextra -Wpedantic -fno-omit-frame-pointer"; \
    done
CMD ["python3", "bench/_entrypoint.py"]
