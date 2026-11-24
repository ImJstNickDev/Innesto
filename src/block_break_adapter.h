#ifndef INNESTO_BLOCK_BREAK_ADAPTER_H
#define INNESTO_BLOCK_BREAK_ADAPTER_H

#include <innesto/block_break.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The version adapter calls this from its installed decision site's startup
 * code, before mod initialization. On success, store the dispatcher at site
 * and return 1. On failure, leave the destination untouched and return 0.
 * The adapter forwards valid attempts on the simulation thread after startup. */
__attribute__((visibility("default")))
int innesto_adapter_attach_before_block_break_v1(innesto_before_block_break_v1 *site);

/* Loader-private startup steps. */
void innesto_block_break_bypass(void);
void innesto_block_break_seal_adapter(void);
void innesto_block_break_open_registration(void);
void innesto_block_break_finish_registration(void);

#ifdef __cplusplus
}
#endif

#endif
