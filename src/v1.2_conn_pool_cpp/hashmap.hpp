#pragma once

#include <cstddef>
#include <ctime>
#include <deque>
#include <string>
#include <unordered_map>

static constexpr size_t HASHMAP_MAX_KEY = 256;
static constexpr size_t HASHMAP_MAX_VAL = 3072;

class HashMap {
public:
    HashMap(size_t capacity, size_t bucket_count);

    // ttl_seconds == 0 means no expiry. Returns 1 (inserted), 0 (updated), -1
    // (error).
    int set(const char* key, const char* value, time_t ttl_seconds);
    const char* get(const char* key);
    bool del(const char* key);
    size_t count() const;

private:
    struct Entry {
        std::string value;
        time_t expires_at;
    };

    void evict_one();

    std::unordered_map<std::string, Entry> data_;
    std::deque<std::string> order_;
    size_t capacity_;
};
