#define _POSIX_C_SOURCE 200809L

#include "hashmap.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct Entry {
    char *key;
    char *value;
    struct Entry *next;
} Entry;

struct HashMap {
    Entry **buckets;
    size_t bucket_count;
    size_t count;
};

static uint64_t hash_key(const char *key) {
    uint64_t hash = 1469598103934665603ULL;

    for (const unsigned char *p = (const unsigned char *)key; *p != '\0'; ++p) {
        hash ^= (uint64_t)(*p);
        hash *= 1099511628211ULL;
    }

    return hash;
}

static Entry *entry_create(const char *key, const char *value) {
    Entry *entry = (Entry *)calloc(1, sizeof(*entry));
    if (entry == NULL) {
        return NULL;
    }

    entry->key = strdup(key);
    entry->value = strdup(value);
    if (entry->key == NULL || entry->value == NULL) {
        free(entry->key);
        free(entry->value);
        free(entry);
        return NULL;
    }

    return entry;
}

HashMap *hashmap_create(size_t bucket_count) {
    if (bucket_count == 0) {
        return NULL;
    }

    HashMap *map = (HashMap *)calloc(1, sizeof(*map));
    if (map == NULL) {
        return NULL;
    }

    map->buckets = (Entry **)calloc(bucket_count, sizeof(*map->buckets));
    if (map->buckets == NULL) {
        free(map);
        return NULL;
    }

    map->bucket_count = bucket_count;
    map->count = 0;
    return map;
}

void hashmap_destroy(HashMap *map) {
    if (map == NULL) {
        return;
    }

    for (size_t i = 0; i < map->bucket_count; ++i) {
        Entry *entry = map->buckets[i];
        while (entry != NULL) {
            Entry *next = entry->next;
            free(entry->key);
            free(entry->value);
            free(entry);
            entry = next;
        }
    }

    free(map->buckets);
    free(map);
}

int hashmap_set(HashMap *map, const char *key, const char *value) {
    if (map == NULL || key == NULL || value == NULL) {
        return -1;
    }

    size_t idx = (size_t)(hash_key(key) % map->bucket_count);
    Entry *entry = map->buckets[idx];

    while (entry != NULL) {
        if (strcmp(entry->key, key) == 0) {
            char *new_value = strdup(value);
            if (new_value == NULL) {
                return -1;
            }
            free(entry->value);
            entry->value = new_value;
            return 0;
        }
        entry = entry->next;
    }

    Entry *new_entry = entry_create(key, value);
    if (new_entry == NULL) {
        return -1;
    }

    new_entry->next = map->buckets[idx];
    map->buckets[idx] = new_entry;
    map->count++;

    return 1;
}

const char *hashmap_get(const HashMap *map, const char *key) {
    if (map == NULL || key == NULL) {
        return NULL;
    }

    size_t idx = (size_t)(hash_key(key) % map->bucket_count);
    Entry *entry = map->buckets[idx];

    while (entry != NULL) {
        if (strcmp(entry->key, key) == 0) {
            return entry->value;
        }
        entry = entry->next;
    }

    return NULL;
}

int hashmap_del(HashMap *map, const char *key) {
    if (map == NULL || key == NULL) {
        return 0;
    }

    size_t idx = (size_t)(hash_key(key) % map->bucket_count);
    Entry *entry = map->buckets[idx];
    Entry *prev = NULL;

    while (entry != NULL) {
        if (strcmp(entry->key, key) == 0) {
            if (prev == NULL) {
                map->buckets[idx] = entry->next;
            } else {
                prev->next = entry->next;
            }

            free(entry->key);
            free(entry->value);
            free(entry);
            map->count--;
            return 1;
        }

        prev = entry;
        entry = entry->next;
    }

    return 0;
}

size_t hashmap_count(const HashMap *map) {
    if (map == NULL) {
        return 0;
    }
    return map->count;
}
