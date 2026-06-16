#pragma once

#include <cstddef>
#include <cstdint>
#include <ctime>
#include <shared_mutex>
#include <vector>

static constexpr size_t HASHMAP_MAX_KEY = 256;
static constexpr size_t HASHMAP_MAX_VAL = 3072;

class SharedHashMap {
public:
    SharedHashMap(size_t capacity, size_t bucket_count);

    SharedHashMap(const SharedHashMap&) = delete;
    SharedHashMap& operator=(const SharedHashMap&) = delete;

    // Returns 1 (inserted), 0 (updated), -1 (error)
    int set(const char* key, const char* value, time_t ttl_seconds);

    // Copies value into out_buf (null-terminated). Returns true on hit.
    bool get(const char* key, char* out_buf, size_t buf_size) const;

    bool del(const char* key);
    size_t count() const;

private:
    struct Entry {
        char key[HASHMAP_MAX_KEY];
        char value[HASHMAP_MAX_VAL];
        time_t expires_at{0};
        bool occupied{false};
        size_t bucket_idx{0};
        Entry* next{nullptr};
        Entry* prev{nullptr};
    };

    mutable std::shared_mutex mutex_;
    std::vector<Entry> slots_;
    std::vector<Entry*> buckets_;
    size_t count_{0};
    size_t ring_head_{0};

    static uint64_t hash_key(const char* key) noexcept;
    void bucket_remove(Entry* e) noexcept;
    void bucket_insert(Entry* e, size_t idx) noexcept;
    Entry* bucket_find(const char* key, size_t idx) const noexcept;
};
