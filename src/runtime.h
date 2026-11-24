#ifndef INNESTO_PRIVATE_RUNTIME_H
#define INNESTO_PRIVATE_RUNTIME_H

#include <innesto/runtime.h>

struct innesto_mod_context {
    const char *id;
    uint32_t environment;
};

void innesto_seal_capabilities(void);
int innesto_initialize_v2(const struct innesto_mod_context *context,
                          int (*initialize)(const struct innesto_mod_context *));
void innesto_finish_startup(void);

#endif
