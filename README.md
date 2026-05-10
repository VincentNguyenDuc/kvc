# kvc

Key-Value Storage - Performance Engineering Playground

## Goal

How far can I optimize an in-memory Key-Value Storage?

## Protocol

Commands (one per line):

- `SET <key> <value>`
- `GET <key>`
- `DEL <key>`

Responses:

- `OK`
- `VALUE <value>`
- `NOT_FOUND`
- `ERROR`

## Project Layout

- `src/main.c` CLI entry point
- `src/server.c` TCP + epoll event loop
- `src/protocol.c` request parsing
- `src/hashmap.c` in-memory key/value store

## Build

```bash
make
```

## Formatting

Format all C and header files:

```bash
make format
```

Check formatting without modifying files:

```bash
make format-check
```

## Run

```bash
./kvc
```

Optional args:

```bash
./kvc <port> <hashmap_buckets>
```

Defaults:

- `port=8080`
- `hashmap_buckets=1024`

## Quick Manual Test

In terminal 1:

```bash
./kvc
```

In terminal 2:

```bash
nc localhost 8080
SET foo hello
GET foo
DEL foo
GET foo
```

Expected responses:

```text
OK
VALUE hello
OK
NOT_FOUND
```

## Docker Workflow

Docker is the recommended way to develop and run this project from macOS while targeting Linux epoll.

### Build Container Images

```bash
make docker-build
```

### Start a Development Shell (Linux)

```bash
make docker-dev
```

Inside the container:

```bash
make clean && make
./kvc 8080 1024
make format-check
```

### Run the Server Container

```bash
make docker-run
```

This publishes port 8080 from the container to your host.

### Test from Host

```bash
nc localhost 8080
SET foo hello
GET foo
DEL foo
```

### Stop Containers

```bash
make docker-stop
```
