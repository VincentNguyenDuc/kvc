#include "server.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>

int main(int argc, char** argv) {
    ServerConfig config;

    if (argc >= 2) {
        char* end = nullptr;
        long port = strtol(argv[1], &end, 10);
        if (errno != 0 || end == argv[1] || *end != '\0' || port <= 0 || port > 65535) {
            fprintf(stderr, "invalid port: %s\n", argv[1]);
            return 1;
        }
        config.port = static_cast<uint16_t>(port);
    }

    if (argc >= 3) {
        char* end = nullptr;
        long buckets = strtol(argv[2], &end, 10);
        if (errno != 0 || end == argv[2] || *end != '\0' || buckets <= 0) {
            fprintf(stderr, "invalid bucket count: %s\n", argv[2]);
            return 1;
        }
        config.hashmap_buckets = static_cast<size_t>(buckets);
    }

    if (argc >= 4) {
        char* end = nullptr;
        long capacity = strtol(argv[3], &end, 10);
        if (errno != 0 || end == argv[3] || *end != '\0' || capacity <= 0) {
            fprintf(stderr, "invalid capacity: %s\n", argv[3]);
            return 1;
        }
        config.hashmap_capacity = static_cast<size_t>(capacity);
    }

    if (argc >= 5) {
        char* end = nullptr;
        long threads = strtol(argv[4], &end, 10);
        if (errno != 0 || end == argv[4] || *end != '\0' || threads <= 0) {
            fprintf(stderr, "invalid thread count: %s\n", argv[4]);
            return 1;
        }
        config.num_threads = static_cast<unsigned int>(threads);
    }

    return run_server(config);
}
