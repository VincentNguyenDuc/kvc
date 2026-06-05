#include "hashmap.hpp"

#include <ctime>

HashMap::HashMap(size_t capacity, size_t bucket_count) : capacity_(capacity) {
    data_.reserve(bucket_count);
}

void HashMap::evict_one() {
    while (!order_.empty()) {
        std::string k = std::move(order_.front());
        order_.pop_front();
        auto it = data_.find(k);
        if (it != data_.end()) {
            data_.erase(it);
            return;
        }
    }
}

int HashMap::set(const char *key, const char *value, time_t ttl_seconds) {
    if (key == nullptr || value == nullptr)
        return -1;

    std::string k(key);
    std::string v(value);

    if (k.size() >= HASHMAP_MAX_KEY || v.size() >= HASHMAP_MAX_VAL)
        return -1;

    time_t expires = ttl_seconds > 0 ? std::time(nullptr) + ttl_seconds : 0;

    auto it = data_.find(k);
    if (it != data_.end()) {
        it->second.value = std::move(v);
        it->second.expires_at = expires;
        return 0;
    }

    while (data_.size() >= capacity_)
        evict_one();

    order_.push_back(k);
    data_.emplace(std::move(k), Entry{std::move(v), expires});
    return 1;
}

const char *HashMap::get(const char *key) {
    if (key == nullptr)
        return nullptr;

    auto it = data_.find(key);
    if (it == data_.end())
        return nullptr;

    if (it->second.expires_at != 0 && std::time(nullptr) >= it->second.expires_at) {
        data_.erase(it);
        return nullptr;
    }

    return it->second.value.c_str();
}

bool HashMap::del(const char *key) {
    if (key == nullptr)
        return false;
    return data_.erase(key) > 0;
}

size_t HashMap::count() const {
    return data_.size();
}
