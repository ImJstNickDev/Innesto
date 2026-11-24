#include <innesto/block_break.h>
#include <innesto/runtime.h>

#include <inttypes.h>
#include <stdio.h>

static const struct innesto_common_v1 *common;
static const char *physical;

static int inspect(const struct innesto_block_break_v1 *event)
{
    fprintf(stderr, "inspect %s/%s %" PRId32 ",%" PRId32 ",%" PRId32 "\n", physical,
            common->logical_side() == INNESTO_LOGICAL_SERVER ? "server" : "unexpected",
            event->x, event->y, event->z);
    return event->x == 0 ? INNESTO_BREAK_VETO : INNESTO_BREAK_PASS;
}

int innesto_mod_init_v2(const struct innesto_mod_context *context)
{
    common = innesto_query_capability_v1(context, INNESTO_CAP_COMMON, 1);
    if (!common || common->logical_side() != INNESTO_LOGICAL_UNKNOWN) {
        return 1;
    }
    physical = common->physical_environment(context) == INNESTO_PHYSICAL_SERVER ? "server" : "client";
    const struct innesto_before_block_break_api_v1 *api =
        innesto_query_capability_v1(context, INNESTO_CAP_BEFORE_BLOCK_BREAK, 1);
    if (!api) {
        fputs("inspect unavailable\n", stderr);
        return innesto_register_before_block_break_v1(inspect) != INNESTO_BREAK_UNAVAILABLE;
    }
    return api->register_listener(inspect) != INNESTO_BREAK_REGISTERED;
}
