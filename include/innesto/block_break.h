#ifndef INNESTO_BLOCK_BREAK_H
#define INNESTO_BLOCK_BREAK_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Coordinates of the proposed edit. The host owns this snapshot for the call. */
struct innesto_block_break_v1 {
    int32_t x;
    int32_t y;
    int32_t z;
};

enum {
    INNESTO_BREAK_PASS = 0,
    INNESTO_BREAK_VETO = 1
};

typedef int (*innesto_before_block_break_v1)(const struct innesto_block_break_v1 *attempt);

enum {
    INNESTO_BREAK_REGISTERED = 0,
    INNESTO_BREAK_UNAVAILABLE = 1,
    INNESTO_BREAK_INVALID = 2,
    INNESTO_BREAK_CLOSED = 3,
    INNESTO_BREAK_NO_MEMORY = 4
};

/* Call during mod initialization. Registration requires a connected simulation host. */
__attribute__((visibility("default")))
int innesto_register_before_block_break_v1(innesto_before_block_break_v1 listener);

#ifdef __cplusplus
}
#endif

#endif
