#pragma once

#include <cstddef>
#include <cstdint>

struct ServerConfig {
    uint16_t port{8080};
    size_t hashmap_capacity{4096};
    size_t hashmap_buckets{1024};
    unsigned int num_threads{0}; // 0 = auto (hardware_concurrency)
};

int run_server(const ServerConfig& config);
