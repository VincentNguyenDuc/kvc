#include "arena.h"

#include <stdint.h>
#include <stdlib.h>

struct Arena {
    unsigned char *buf;
    size_t offset;
    size_t capacity;
};

/* Round `n` up to the next multiple of `align` (power-of-two align). */
static size_t align_up(size_t n, size_t align) { return (n + align - 1) & ~(align - 1); }

static int is_power_of_two(size_t n) { return n != 0 && (n & (n - 1)) == 0; }

Arena *arena_create(size_t capacity) {
    if (capacity == 0)
        return NULL;

    Arena *a = malloc(sizeof(*a));
    if (a == NULL)
        return NULL;

    a->buf = malloc(capacity);
    if (a->buf == NULL) {
        free(a);
        return NULL;
    }

    a->offset = 0;
    a->capacity = capacity;
    return a;
}

void arena_destroy(Arena *a) {
    if (a == NULL)
        return;
    free(a->buf);
    free(a);
}

void *arena_alloc_aligned(Arena *a, size_t size, size_t align) {
    if (a == NULL || size == 0 || !is_power_of_two(align))
        return NULL;

    /* Compute the aligned start offset relative to the buffer base. */
    uintptr_t base = (uintptr_t)a->buf + a->offset;
    uintptr_t aligned = align_up(base, align);
    size_t padding = (size_t)(aligned - base);

    if (a->capacity - a->offset < padding + size)
        return NULL;

    a->offset += padding + size;
    return (void *)aligned;
}

void *arena_alloc(Arena *a, size_t size) {
    return arena_alloc_aligned(a, size, ARENA_DEFAULT_ALIGN);
}

void arena_reset(Arena *a) {
    if (a != NULL)
        a->offset = 0;
}

size_t arena_used(const Arena *a) { return a != NULL ? a->offset : 0; }

size_t arena_capacity(const Arena *a) { return a != NULL ? a->capacity : 0; }
