#include "protocol.h"

#include <string.h>

int parse_request(char* line, size_t len, Request* out) {
    if (line == NULL || out == NULL)
        return -1;

    /* caller replaced \n with \0; strip a trailing \r if present */
    if (len > 0 && line[len - 1] == '\r')
        line[--len] = '\0';

    if (len == 0)
        return -1;

    char* end = line + len;
    char* p = line;

    while (p < end && (*p == ' ' || *p == '\t'))
        p++;
    if (p == end)
        return -1;

    char* cmd = p;
    char* cmd_end = memchr(p, ' ', (size_t)(end - p));
    size_t cmd_len = cmd_end != NULL ? (size_t)(cmd_end - cmd) : (size_t)(end - cmd);

    if (cmd_len != 3)
        return -1;

    p = cmd_end != NULL ? cmd_end : end;
    while (p < end && (*p == ' ' || *p == '\t'))
        p++;

    if (cmd[0] == 'G' && cmd[1] == 'E' && cmd[2] == 'T') {
        if (p == end)
            return -1;

        char* key = p;
        char* key_end = memchr(p, ' ', (size_t)(end - p));
        size_t klen;
        if (key_end != NULL) {
            char* trail = key_end;
            while (trail < end && (*trail == ' ' || *trail == '\t'))
                trail++;
            if (trail != end)
                return -1;
            klen = (size_t)(key_end - key);
        } else {
            klen = (size_t)(end - key);
        }
        if (klen == 0 || klen >= sizeof(out->key))
            return -1;

        memcpy(out->key, key, klen);
        out->key[klen] = '\0';
        out->type = CMD_GET;
        return 0;
    }

    if (cmd[0] == 'D' && cmd[1] == 'E' && cmd[2] == 'L') {
        if (p == end)
            return -1;

        char* key = p;
        char* key_end = memchr(p, ' ', (size_t)(end - p));
        size_t klen;
        if (key_end != NULL) {
            char* trail = key_end;
            while (trail < end && (*trail == ' ' || *trail == '\t'))
                trail++;
            if (trail != end)
                return -1;
            klen = (size_t)(key_end - key);
        } else {
            klen = (size_t)(end - key);
        }
        if (klen == 0 || klen >= sizeof(out->key))
            return -1;

        memcpy(out->key, key, klen);
        out->key[klen] = '\0';
        out->type = CMD_DEL;
        return 0;
    }

    if (cmd[0] == 'S' && cmd[1] == 'E' && cmd[2] == 'T') {
        if (p == end)
            return -1;

        char* key = p;
        char* key_end = memchr(p, ' ', (size_t)(end - p));
        if (key_end == NULL)
            return -1;

        size_t klen = (size_t)(key_end - key);
        if (klen == 0 || klen >= sizeof(out->key))
            return -1;

        char* val = key_end;
        while (val < end && (*val == ' ' || *val == '\t'))
            val++;
        if (val == end)
            return -1;

        size_t vlen = (size_t)(end - val);
        if (vlen >= sizeof(out->value))
            return -1;

        memcpy(out->key, key, klen);
        out->key[klen] = '\0';
        memcpy(out->value, val, vlen);
        out->value[vlen] = '\0';
        out->type = CMD_SET;
        return 0;
    }

    return -1;
}
