#include "server.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    ServerConfig config;
    config.port = 8080;
    config.hashmap_capacity = 4096;
    config.hashmap_buckets = 1024;

    if (argc >= 2) {
        char *end = NULL;
        long port = strtol(argv[1], &end, 10);
        if (errno != 0 || end == argv[1] || *end != '\0' || port <= 0 || port > 65535) {
            fprintf(stderr, "invalid port: %s\n", argv[1]);
            return 1;
        }
        config.port = (unsigned short)port;
    }

    if (argc >= 3) {
        char *end = NULL;
        long buckets = strtol(argv[2], &end, 10);
        if (errno != 0 || end == argv[2] || *end != '\0' || buckets <= 0) {
            fprintf(stderr, "invalid bucket count: %s\n", argv[2]);
            return 1;
        }
        config.hashmap_buckets = (size_t)buckets;
    }

    if (argc >= 4) {
        char *end = NULL;
        long capacity = strtol(argv[3], &end, 10);
        if (errno != 0 || end == argv[3] || *end != '\0' || capacity <= 0) {
            fprintf(stderr, "invalid capacity: %s\n", argv[3]);
            return 1;
        }
        config.hashmap_capacity = (size_t)capacity;
    }

    return run_server(&config);
}
