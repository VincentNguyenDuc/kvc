#ifndef SERVER_H
#define SERVER_H

#include <stdint.h>
#include <stddef.h>

typedef struct ServerConfig {
    uint16_t port;
    size_t hashmap_buckets;
} ServerConfig;

int run_server(const ServerConfig *config);

#endif
