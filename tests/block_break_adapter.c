#include "fixture_break_adapter.h"
#include "block_break_adapter.h"

/* The adapted fixture also runs as an ordinary executable without Innesto. */
extern int innesto_adapter_attach_before_block_break_v1(innesto_before_block_break_v1 *site)
    __attribute__((weak));

static innesto_before_block_break_v1 before_break;

void fixture_install_break_adapter(void)
{
    if (innesto_adapter_attach_before_block_break_v1) {
        innesto_adapter_attach_before_block_break_v1(&before_break);
    }
}

int fixture_dispatch_break(int32_t x, int32_t y, int32_t z)
{
    if (!before_break) {
        return 1;
    }
    const struct innesto_block_break_v1 attempt = {.x = x, .y = y, .z = z};
    return before_break(&attempt) == INNESTO_BREAK_PASS;
}
