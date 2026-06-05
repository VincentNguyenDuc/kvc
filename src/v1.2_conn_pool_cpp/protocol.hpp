#pragma once

#include <cstddef>

enum { PROTOCOL_MAX_LINE = 4096, PROTOCOL_MAX_KEY = 256, PROTOCOL_MAX_VALUE = 3072 };

enum class CommandType { Invalid = 0, Get, Set, Del };

struct Request {
    CommandType type;
    char key[PROTOCOL_MAX_KEY];
    char value[PROTOCOL_MAX_VALUE];
};

int parse_request(char *line, size_t len, Request &out);
