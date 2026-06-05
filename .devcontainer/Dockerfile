FROM debian:bookworm-slim

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        clang-format \
        make \
        gdb \
        strace \
        netcat-openbsd \
        ca-certificates \
        openssh-client \
        curl \
        git \
        linux-perf \
        python3 \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN curl -fsSL https://starship.rs/install.sh | sh -s -- -y \
   && echo 'eval "$(starship init bash)"' >> /etc/bash.bashrc

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

CMD ["bash"]
