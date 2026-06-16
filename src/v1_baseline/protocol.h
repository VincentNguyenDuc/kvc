#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stddef.h>

enum { PROTOCOL_MAX_LINE = 4096, PROTOCOL_MAX_KEY = 256, PROTOCOL_MAX_VALUE = 3072 };

typedef enum CommandType { CMD_INVALID = 0, CMD_GET, CMD_SET, CMD_DEL } CommandType;

typedef struct Request {
    CommandType type;
    char key[PROTOCOL_MAX_KEY];
    char value[PROTOCOL_MAX_VALUE];
} Request;

int parse_request(const char* line, Request* out);

#endif
