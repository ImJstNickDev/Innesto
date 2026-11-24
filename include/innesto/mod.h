#ifndef INNESTO_MOD_H
#define INNESTO_MOD_H

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Implement this entrypoint in the mod. Innesto calls it once during process
 * startup, before the host's main function. Return zero to continue startup.
 */
__attribute__((visibility("default"))) int innesto_mod_init_v1(void);

#ifdef __cplusplus
}
#endif

#endif
