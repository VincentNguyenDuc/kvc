#ifndef HASHMAP_H
#define HASHMAP_H

#include <stddef.h>
#include <time.h>

#define HASHMAP_MAX_KEY 256
#define HASHMAP_MAX_VAL 3072

typedef struct HashMap HashMap;

HashMap* hashmap_create(size_t capacity, size_t bucket_count);
void hashmap_destroy(HashMap* map);

/* ttl_seconds == 0 means no expiry. Returns 1 (inserted), 0 (updated), -1
 * (error). */
int hashmap_set(HashMap* map, const char* key, const char* value, time_t ttl_seconds);
const char* hashmap_get(HashMap* map, const char* key);
int hashmap_del(HashMap* map, const char* key);
size_t hashmap_count(const HashMap* map);

#endif
