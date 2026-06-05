#define _POSIX_C_SOURCE 200809L

#include "hashmap.h"
#include "arena.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct Entry {
    char key[HASHMAP_MAX_KEY];
    char value[HASHMAP_MAX_VAL];
    time_t expires_at; /* 0 = no expiry */
    int occupied;
    size_t bucket_idx;
    struct Entry *next; /* doubly-linked bucket chain for O(1) removal */
    struct Entry *prev;
} Entry;

struct HashMap {
    Arena *arena;
    Entry *slots;    /* ring buffer slab, allocated from arena */
    Entry **buckets; /* pointer table, allocated from arena */
    size_t bucket_count;
    size_t capacity;
    size_t count;
    size_t ring_head; /* next slot to evict/fill (FIFO) */
};

static uint64_t hash_key(const char *key) {
    uint64_t h = 1469598103934665603ULL;
    for (const unsigned char *p = (const unsigned char *)key; *p; ++p) {
        h ^= (uint64_t)(*p);
        h *= 1099511628211ULL;
    }
    return h;
}

static void bucket_remove(HashMap *map, Entry *e) {
    if (e->prev)
        e->prev->next = e->next;
    else
        map->buckets[e->bucket_idx] = e->next;
    if (e->next)
        e->next->prev = e->prev;
    e->next = e->prev = NULL;
}

static void bucket_insert(HashMap *map, Entry *e, size_t idx) {
    e->bucket_idx = idx;
    e->prev = NULL;
    e->next = map->buckets[idx];
    if (map->buckets[idx])
        map->buckets[idx]->prev = e;
    map->buckets[idx] = e;
}

static Entry *bucket_find(HashMap *map, const char *key, size_t idx) {
    for (Entry *e = map->buckets[idx]; e; e = e->next)
        if (strcmp(e->key, key) == 0)
            return e;
    return NULL;
}

HashMap *hashmap_create(size_t capacity, size_t bucket_count) {
    if (capacity == 0 || bucket_count == 0)
        return NULL;

    size_t arena_size = capacity * sizeof(Entry) + bucket_count * sizeof(Entry *);
    Arena *arena = arena_create(arena_size);
    if (!arena)
        return NULL;

    HashMap *map = calloc(1, sizeof(*map));
    if (!map) {
        arena_destroy(arena);
        return NULL;
    }

    map->slots = arena_alloc_aligned(arena, capacity * sizeof(Entry), _Alignof(Entry));
    map->buckets = arena_alloc_aligned(arena, bucket_count * sizeof(Entry *), _Alignof(Entry *));
    if (!map->slots || !map->buckets) {
        free(map);
        arena_destroy(arena);
        return NULL;
    }

    memset(map->slots, 0, capacity * sizeof(Entry));
    memset(map->buckets, 0, bucket_count * sizeof(Entry *));

    map->arena = arena;
    map->capacity = capacity;
    map->bucket_count = bucket_count;
    return map;
}

void hashmap_destroy(HashMap *map) {
    if (!map)
        return;
    arena_destroy(map->arena);
    free(map);
}

int hashmap_set(HashMap *map, const char *key, const char *value, time_t ttl_seconds) {
    if (!map || !key || !value)
        return -1;

    size_t klen = strlen(key);
    size_t vlen = strlen(value);
    if (klen >= HASHMAP_MAX_KEY || vlen >= HASHMAP_MAX_VAL)
        return -1;

    size_t idx = (size_t)(hash_key(key) % map->bucket_count);
    Entry *e = bucket_find(map, key, idx);

    if (e) {
        memcpy(e->value, value, vlen + 1);
        e->expires_at = ttl_seconds > 0 ? time(NULL) + ttl_seconds : 0;
        return 0;
    }

    Entry *slot = &map->slots[map->ring_head];
    map->ring_head = (map->ring_head + 1) % map->capacity;

    if (slot->occupied) {
        bucket_remove(map, slot);
        map->count--;
    }

    memcpy(slot->key, key, klen + 1);
    memcpy(slot->value, value, vlen + 1);
    slot->expires_at = ttl_seconds > 0 ? time(NULL) + ttl_seconds : 0;
    slot->occupied = 1;

    bucket_insert(map, slot, idx);
    map->count++;
    return 1;
}

const char *hashmap_get(HashMap *map, const char *key) {
    if (!map || !key)
        return NULL;

    size_t idx = (size_t)(hash_key(key) % map->bucket_count);
    Entry *e = bucket_find(map, key, idx);
    if (!e)
        return NULL;

    if (e->expires_at != 0 && time(NULL) >= e->expires_at) {
        bucket_remove(map, e);
        e->occupied = 0;
        map->count--;
        return NULL;
    }

    return e->value;
}

int hashmap_del(HashMap *map, const char *key) {
    if (!map || !key)
        return 0;

    size_t idx = (size_t)(hash_key(key) % map->bucket_count);
    Entry *e = bucket_find(map, key, idx);
    if (!e)
        return 0;

    bucket_remove(map, e);
    e->occupied = 0;
    map->count--;
    return 1;
}

size_t hashmap_count(const HashMap *map) { return map ? map->count : 0; }
