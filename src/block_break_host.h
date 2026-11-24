#ifndef INNESTO_BLOCK_BREAK_HOST_H
#define INNESTO_BLOCK_BREAK_HOST_H

#include <innesto/block_break.h>

#ifdef __cplusplus
extern "C" {
#endif

/* An opting-in host stores this callback and calls it on its simulation thread
 * before committing a validated player break. The host owns commit and reply. */
__attribute__((visibility("default")))
void innesto_host_set_before_block_break_v1(innesto_before_block_break_v1 callback);

/* Loader-private initialization steps. */
void innesto_block_break_open_registration(void);
void innesto_block_break_finish_registration(void);

#ifdef __cplusplus
}
#endif

#endif
