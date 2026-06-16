#include "protocol.h"

#include <ctype.h>
#include <string.h>

static char* skip_spaces(char* s) {
    while (*s != '\0' && isspace((unsigned char)*s)) {
        s++;
    }
    return s;
}

int parse_request(const char* line, Request* out) {
    if (line == NULL || out == NULL) {
        return -1;
    }

    memset(out, 0, sizeof(*out));

    char buf[PROTOCOL_MAX_LINE];
    size_t n = strlen(line);
    if (n >= sizeof(buf)) {
        return -1;
    }

    memcpy(buf, line, n + 1);
    while (n > 0 && (buf[n - 1] == '\n' || buf[n - 1] == '\r')) {
        buf[n - 1] = '\0';
        n--;
    }

    char* cursor = skip_spaces(buf);
    if (*cursor == '\0') {
        return -1;
    }

    char* cmd = cursor;
    while (*cursor != '\0' && !isspace((unsigned char)*cursor)) {
        cursor++;
    }
    if (*cursor != '\0') {
        *cursor++ = '\0';
    }
    cursor = skip_spaces(cursor);

    if (strcmp(cmd, "GET") == 0) {
        if (*cursor == '\0') {
            return -1;
        }

        char* key = cursor;
        while (*cursor != '\0' && !isspace((unsigned char)*cursor)) {
            cursor++;
        }
        if (*cursor != '\0') {
            *cursor++ = '\0';
            cursor = skip_spaces(cursor);
            if (*cursor != '\0') {
                return -1;
            }
        }

        if (strlen(key) >= sizeof(out->key)) {
            return -1;
        }

        out->type = CMD_GET;
        strcpy(out->key, key);
        return 0;
    }

    if (strcmp(cmd, "DEL") == 0) {
        if (*cursor == '\0') {
            return -1;
        }

        char* key = cursor;
        while (*cursor != '\0' && !isspace((unsigned char)*cursor)) {
            cursor++;
        }
        if (*cursor != '\0') {
            *cursor++ = '\0';
            cursor = skip_spaces(cursor);
            if (*cursor != '\0') {
                return -1;
            }
        }

        if (strlen(key) >= sizeof(out->key)) {
            return -1;
        }

        out->type = CMD_DEL;
        strcpy(out->key, key);
        return 0;
    }

    if (strcmp(cmd, "SET") == 0) {
        if (*cursor == '\0') {
            return -1;
        }

        char* key = cursor;
        while (*cursor != '\0' && !isspace((unsigned char)*cursor)) {
            cursor++;
        }

        if (*cursor == '\0') {
            return -1;
        }

        *cursor++ = '\0';
        cursor = skip_spaces(cursor);
        if (*cursor == '\0') {
            return -1;
        }

        if (strlen(key) >= sizeof(out->key) || strlen(cursor) >= sizeof(out->value)) {
            return -1;
        }

        out->type = CMD_SET;
        strcpy(out->key, key);
        strcpy(out->value, cursor);
        return 0;
    }

    return -1;
}
