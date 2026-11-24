/* Registered after the example guard to observe cross-mod short circuiting. */
#include <innesto/block_break.h>
#include <innesto/mod.h>

#include <inttypes.h>
#include <stdio.h>

static int observe(const struct innesto_block_break_v1 *event)
{
    fprintf(stderr, "probe %" PRId32 ",%" PRId32 ",%" PRId32 "\n", event->x, event->y, event->z);
    return INNESTO_BREAK_PASS;
}

int innesto_mod_init_v1(void)
{
    return innesto_register_before_block_break_v1(observe) != INNESTO_BREAK_REGISTERED;
}
