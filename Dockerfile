FROM debian:bookworm-slim AS base

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

FROM base AS dev
CMD ["bash"]

FROM base AS run
COPY . /workspace
RUN make clean && make
EXPOSE 8080
CMD ["./kvc", "8080", "1024"]
