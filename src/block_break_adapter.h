#ifndef INNESTO_BLOCK_BREAK_ADAPTER_H
#define INNESTO_BLOCK_BREAK_ADAPTER_H

#include <innesto/block_break.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Publish a successfully bound decision on this physical target. On failure,
 * leave the destination untouched so the version adapter can roll back. */
int innesto_adapter_attach_before_block_break_v1(innesto_before_block_break_v1 *site, uint32_t physical);

/* Loader-private startup steps. */
void innesto_block_break_bypass(void);
void innesto_block_break_seal_adapter(void);
void innesto_block_break_open_registration(void);
void innesto_block_break_finish_registration(void);

#ifdef __cplusplus
}
#endif

#endif
