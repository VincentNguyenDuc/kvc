#include "hashmap.hpp"

#include <cstring>
#include <ctime>
#include <mutex>

uint64_t SharedHashMap::hash_key(const char* key) noexcept {
    uint64_t h = 1469598103934665603ULL;
    for (const auto* p = reinterpret_cast<const unsigned char*>(key); *p; ++p) {
        h ^= static_cast<uint64_t>(*p);
        h *= 1099511628211ULL;
    }
    return h;
}

void SharedHashMap::bucket_remove(Entry* e) noexcept {
    if (e->prev)
        e->prev->next = e->next;
    else
        buckets_[e->bucket_idx] = e->next;
    if (e->next)
        e->next->prev = e->prev;
    e->next = e->prev = nullptr;
}

void SharedHashMap::bucket_insert(Entry* e, size_t idx) noexcept {
    e->bucket_idx = idx;
    e->prev = nullptr;
    e->next = buckets_[idx];
    if (buckets_[idx])
        buckets_[idx]->prev = e;
    buckets_[idx] = e;
}

SharedHashMap::Entry* SharedHashMap::bucket_find(const char* key, size_t idx) const noexcept {
    for (Entry* e = buckets_[idx]; e; e = e->next)
        if (strcmp(e->key, key) == 0)
            return e;
    return nullptr;
}

SharedHashMap::SharedHashMap(size_t capacity, size_t bucket_count)
    : slots_(capacity)
    , buckets_(bucket_count, nullptr) {}

int SharedHashMap::set(const char* key, const char* value, time_t ttl_seconds) {
    if (slots_.empty() || !key || !value)
        return -1;

    size_t klen = strlen(key);
    size_t vlen = strlen(value);
    if (klen >= HASHMAP_MAX_KEY || vlen >= HASHMAP_MAX_VAL)
        return -1;

    size_t idx = static_cast<size_t>(hash_key(key) % buckets_.size());

    std::unique_lock lock(mutex_);

    Entry* e = bucket_find(key, idx);
    if (e) {
        memcpy(e->value, value, vlen + 1);
        e->expires_at = ttl_seconds > 0 ? time(nullptr) + ttl_seconds : 0;
        return 0;
    }

    Entry* slot = &slots_[ring_head_];
    ring_head_ = (ring_head_ + 1) % slots_.size();

    if (slot->occupied) {
        bucket_remove(slot);
        count_--;
    }

    memcpy(slot->key, key, klen + 1);
    memcpy(slot->value, value, vlen + 1);
    slot->expires_at = ttl_seconds > 0 ? time(nullptr) + ttl_seconds : 0;
    slot->occupied = true;

    bucket_insert(slot, idx);
    count_++;
    return 1;
}

bool SharedHashMap::get(const char* key, char* out_buf, size_t buf_size) const {
    if (slots_.empty() || !key || !out_buf || buf_size == 0)
        return false;

    size_t idx = static_cast<size_t>(hash_key(key) % buckets_.size());

    std::shared_lock lock(mutex_);

    Entry* e = bucket_find(key, idx);
    if (!e)
        return false;

    // Expired entries are lazily cleaned up by SET; just report miss here.
    if (e->expires_at != 0 && time(nullptr) >= e->expires_at)
        return false;

    size_t vlen = strlen(e->value);
    if (vlen + 1 > buf_size)
        return false;

    memcpy(out_buf, e->value, vlen + 1);
    return true;
}

bool SharedHashMap::del(const char* key) {
    if (slots_.empty() || !key)
        return false;

    size_t idx = static_cast<size_t>(hash_key(key) % buckets_.size());

    std::unique_lock lock(mutex_);

    Entry* e = bucket_find(key, idx);
    if (!e)
        return false;

    bucket_remove(e);
    e->occupied = false;
    count_--;
    return true;
}

size_t SharedHashMap::count() const {
    std::shared_lock lock(mutex_);
    return count_;
}
