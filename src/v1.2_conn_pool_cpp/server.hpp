#pragma once

#include <cstddef>
#include <cstdint>

struct ServerConfig {
    uint16_t port;
    size_t hashmap_capacity;
    size_t hashmap_buckets;
};

int run_server(const ServerConfig& config);
