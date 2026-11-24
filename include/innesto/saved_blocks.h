#ifndef INNESTO_SAVED_BLOCKS_H
#define INNESTO_SAVED_BLOCKS_H

#include <stdint.h>

#define INNESTO_CAP_SAVED_BLOCKS "innesto.server.saved_blocks"

struct innesto_saved_block_totals_v1 {
    uint64_t broken;
    uint64_t placed;
};

enum innesto_saved_blocks_status {
    INNESTO_SAVED_BLOCKS_OK = 0,
    INNESTO_SAVED_BLOCKS_INVALID_ARGUMENT,
    INNESTO_SAVED_BLOCKS_NOT_FOUND,
    INNESTO_SAVED_BLOCKS_UNREADABLE,
    INNESTO_SAVED_BLOCKS_INVALID_RECORD
};

/* Version 1. Each call reads the latest persisted record in the bound
 * directory. The caller supplies a lowercase, hyphenated player UUID.
 * Both output fields are written together on success only. */
struct innesto_saved_blocks_v1 {
    int (*read)(const char *player_uuid, struct innesto_saved_block_totals_v1 *out);
};

#endif
