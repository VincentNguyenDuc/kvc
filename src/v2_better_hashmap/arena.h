#ifndef ARENA_H
#define ARENA_H

#include <stddef.h>

/* Default alignment matches the strictest scalar type on the platform. */
#define ARENA_DEFAULT_ALIGN (_Alignof(max_align_t))

typedef struct Arena Arena;

/* Allocate a new arena backed by a contiguous block of `capacity` bytes. */
Arena* arena_create(size_t capacity);

/* Free the arena and its entire backing buffer. */
void arena_destroy(Arena* arena);

/*
 * Bump-allocate `size` bytes aligned to ARENA_DEFAULT_ALIGN.
 * Returns NULL if the arena is exhausted.
 */
void* arena_alloc(Arena* arena, size_t size);

/*
 * Bump-allocate `size` bytes aligned to `align` (must be a power of two).
 * Returns NULL if the arena is exhausted or `align` is invalid.
 */
void* arena_alloc_aligned(Arena* arena, size_t size, size_t align);

/*
 * Reset the bump pointer to zero without freeing the backing buffer.
 * All previously returned pointers become invalid.
 */
void arena_reset(Arena* arena);

/* Bytes consumed since creation or last reset. */
size_t arena_used(const Arena* arena);

/* Total capacity in bytes. */
size_t arena_capacity(const Arena* arena);

#endif
