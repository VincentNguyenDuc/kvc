#include "server.hpp"

#include "hashmap.hpp"
#include "protocol.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#ifdef __linux__
#include <sys/epoll.h>
#endif
#include <sys/socket.h>
#include <unistd.h>

#ifndef __linux__

int run_server(const ServerConfig &) {
    fprintf(stderr, "kvc requires Linux for epoll support.\n");
    return 1;
}

#else

static constexpr int MAX_EVENTS = 128;
static constexpr int MAX_FDS = 65536;
static constexpr int CLIENT_POOL_SIZE = 512;

struct Client {
    int fd;
    size_t used;
    char buffer[PROTOCOL_MAX_LINE];
};

static Client g_pool[CLIENT_POOL_SIZE];
static int g_free[CLIENT_POOL_SIZE];
static int g_free_top;

static void pool_init() {
    for (int i = 0; i < CLIENT_POOL_SIZE; ++i)
        g_free[i] = i;
    g_free_top = CLIENT_POOL_SIZE;
}

static Client *pool_alloc() {
    if (g_free_top == 0)
        return nullptr;
    int idx = g_free[--g_free_top];
    memset(&g_pool[idx], 0, sizeof(g_pool[idx]));
    return &g_pool[idx];
}

static void pool_free(Client *c) {
    int idx = static_cast<int>(c - g_pool);
    g_free[g_free_top++] = idx;
}

static int set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags == -1)
        return -1;
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK) == -1 ? -1 : 0;
}

static int create_listen_socket(uint16_t port) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd == -1) {
        perror("socket");
        return -1;
    }

    int reuse = 1;
    if (setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse)) == -1) {
        perror("setsockopt(SO_REUSEADDR)");
        close(fd);
        return -1;
    }

    if (set_nonblocking(fd) == -1) {
        perror("set_nonblocking(listen)");
        close(fd);
        return -1;
    }

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) == -1) {
        perror("bind");
        close(fd);
        return -1;
    }

    if (listen(fd, 1024) == -1) {
        perror("listen");
        close(fd);
        return -1;
    }

    return fd;
}

static void close_client(int epoll_fd, Client **clients, int fd) {
    if (fd < 0 || fd >= MAX_FDS)
        return;
    epoll_ctl(epoll_fd, EPOLL_CTL_DEL, fd, nullptr);
    if (clients[fd] != nullptr) {
        pool_free(clients[fd]);
        clients[fd] = nullptr;
    }
    close(fd);
}

static int send_response(int fd, const char *msg) {
    size_t len = strlen(msg);
    size_t sent = 0;

    while (sent < len) {
        ssize_t n = send(fd, msg + sent, len - sent, MSG_NOSIGNAL);
        if (n > 0) {
            sent += static_cast<size_t>(n);
            continue;
        }
        if (n == -1 && errno == EINTR)
            continue;
        if (n == -1 && (errno == EAGAIN || errno == EWOULDBLOCK))
            return 0;
        return -1;
    }

    return 0;
}

static int handle_line(int fd, HashMap &map, char *line, size_t len) {
    Request req{};
    if (parse_request(line, len, req) != 0)
        return send_response(fd, "ERROR\n");

    switch (req.type) {
    case CommandType::Set:
        if (map.set(req.key, req.value, 0) < 0)
            return send_response(fd, "ERROR\n");
        return send_response(fd, "OK\n");

    case CommandType::Get: {
        const char *value = map.get(req.key);
        if (value == nullptr)
            return send_response(fd, "NOT_FOUND\n");
        char out[PROTOCOL_MAX_VALUE + 16];
        size_t vlen = strlen(value);
        memcpy(out, "VALUE ", 6);
        memcpy(out + 6, value, vlen);
        out[6 + vlen] = '\n';
        out[6 + vlen + 1] = '\0';
        return send_response(fd, out);
    }

    case CommandType::Del:
        return send_response(fd, map.del(req.key) ? "OK\n" : "NOT_FOUND\n");

    default:
        return send_response(fd, "ERROR\n");
    }
}

static int handle_client_read(int epoll_fd, Client **clients, int fd, HashMap &map) {
    Client *client = clients[fd];
    if (client == nullptr)
        return -1;

    for (;;) {
        if (client->used >= sizeof(client->buffer)) {
            if (send_response(fd, "ERROR\n") == -1)
                return -1;
            client->used = 0;
        }

        ssize_t n = recv(fd, client->buffer + client->used,
                         sizeof(client->buffer) - client->used, 0);
        if (n > 0) {
            client->used += static_cast<size_t>(n);

            size_t start = 0;
            for (size_t i = 0; i < client->used; ++i) {
                if (client->buffer[i] == '\n') {
                    size_t line_len = i - start;
                    client->buffer[i] = '\0';
                    if (handle_line(fd, map, client->buffer + start, line_len) == -1)
                        return -1;
                    start = i + 1;
                }
            }

            if (start > 0) {
                size_t left = client->used - start;
                memmove(client->buffer, client->buffer + start, left);
                client->used = left;
            }
            continue;
        }

        if (n == 0)
            return -1;
        if (errno == EAGAIN || errno == EWOULDBLOCK)
            return 0;
        if (errno == EINTR)
            continue;
        return -1;
    }

    (void)epoll_fd;
}

static int accept_clients(int epoll_fd, int listen_fd, Client **clients) {
    for (;;) {
        sockaddr_in addr{};
        socklen_t addr_len = sizeof(addr);
        int client_fd = accept(listen_fd, reinterpret_cast<sockaddr *>(&addr), &addr_len);
        if (client_fd == -1) {
            if (errno == EAGAIN || errno == EWOULDBLOCK)
                return 0;
            if (errno == EINTR)
                continue;
            perror("accept");
            return -1;
        }

        if (client_fd >= MAX_FDS) {
            close(client_fd);
            continue;
        }

        if (set_nonblocking(client_fd) == -1) {
            close(client_fd);
            continue;
        }

        Client *client = pool_alloc();
        if (client == nullptr) {
            fprintf(stderr, "connection pool exhausted\n");
            close(client_fd);
            continue;
        }
        client->fd = client_fd;

        epoll_event ev{};
        ev.events = EPOLLIN | EPOLLRDHUP;
        ev.data.fd = client_fd;

        if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, client_fd, &ev) == -1) {
            pool_free(client);
            close(client_fd);
            continue;
        }

        clients[client_fd] = client;
    }
}

int run_server(const ServerConfig &config) {
    signal(SIGPIPE, SIG_IGN);
    pool_init();

    HashMap map(config.hashmap_capacity, config.hashmap_buckets);

    int listen_fd = create_listen_socket(config.port);
    if (listen_fd == -1)
        return 1;

    int epoll_fd = epoll_create1(0);
    if (epoll_fd == -1) {
        perror("epoll_create1");
        close(listen_fd);
        return 1;
    }

    epoll_event listen_ev{};
    listen_ev.events = EPOLLIN;
    listen_ev.data.fd = listen_fd;

    if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, listen_fd, &listen_ev) == -1) {
        perror("epoll_ctl(add listen_fd)");
        close(epoll_fd);
        close(listen_fd);
        return 1;
    }

    Client **clients = static_cast<Client **>(calloc(MAX_FDS, sizeof(*clients)));
    if (clients == nullptr) {
        fprintf(stderr, "failed to allocate client table\n");
        close(epoll_fd);
        close(listen_fd);
        return 1;
    }

    printf("kvc listening on 0.0.0.0:%u\n", config.port);

    epoll_event events[MAX_EVENTS];
    for (;;) {
        int n_ready = epoll_wait(epoll_fd, events, MAX_EVENTS, -1);
        if (n_ready == -1) {
            if (errno == EINTR)
                continue;
            perror("epoll_wait");
            break;
        }

        for (int i = 0; i < n_ready; ++i) {
            int fd = events[i].data.fd;
            uint32_t ev = events[i].events;

            if (fd == listen_fd) {
                if (accept_clients(epoll_fd, listen_fd, clients) == -1)
                    goto shutdown;
                continue;
            }

            if (fd < 0 || fd >= MAX_FDS || clients[fd] == nullptr)
                continue;

            if ((ev & (EPOLLERR | EPOLLHUP | EPOLLRDHUP)) != 0U) {
                close_client(epoll_fd, clients, fd);
                continue;
            }

            if ((ev & EPOLLIN) != 0U) {
                if (handle_client_read(epoll_fd, clients, fd, map) == -1)
                    close_client(epoll_fd, clients, fd);
            }
        }
    }

shutdown:
    for (int fd = 0; fd < MAX_FDS; ++fd) {
        if (clients[fd] != nullptr)
            close_client(epoll_fd, clients, fd);
    }

    free(clients);
    close(epoll_fd);
    close(listen_fd);
    return 0;
}

#endif
