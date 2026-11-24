#include <innesto/block_break.h>
#include <innesto/mod.h>
#include <inttypes.h>
#include <stdio.h>

static int guard_break(const struct innesto_block_break_v1 *attempt)
{
    fprintf(stderr, "guard %" PRId32 ",%" PRId32 ",%" PRId32 "\n",
            attempt->x, attempt->y, attempt->z);
    return attempt->x == 0 ? INNESTO_BREAK_VETO : INNESTO_BREAK_PASS;
}

int innesto_mod_init_v1(void)
{
    int status = innesto_register_before_block_break_v1(guard_break);
    if (status == INNESTO_BREAK_UNAVAILABLE) {
        fputs("break_guard requires a server with before-block-break support\n", stderr);
    } else if (status != INNESTO_BREAK_REGISTERED) {
        fprintf(stderr, "break_guard could not register its listener (status %d)\n", status);
    }
    return status != INNESTO_BREAK_REGISTERED;
}
