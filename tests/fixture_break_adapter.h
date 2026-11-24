#ifndef FIXTURE_BLOCK_BREAK_ADAPTER_H
#define FIXTURE_BLOCK_BREAK_ADAPTER_H

#include <stdint.h>

void fixture_install_break_adapter(void);

/* Returns nonzero if the registered listeners allow this edit. */
int fixture_dispatch_break(int32_t x, int32_t y, int32_t z);

#endif
