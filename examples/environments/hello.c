#include <innesto/runtime.h>
#include <stdio.h>
#include <unistd.h>

static const struct innesto_common_v1 *common;

static void report(const struct innesto_mod_context *context, const char *phase)
{
    const char *side = common->physical_environment(context) == INNESTO_PHYSICAL_CLIENT ? "client" : "server";
    const char *logical = common->logical_side() == INNESTO_LOGICAL_UNKNOWN ? "unknown" : "unexpected";
    fprintf(stderr, "Innesto %s %s physical=%s logical=%s pid=%ld\n",
            common->mod_id(context), phase, side, logical, (long)getpid());
}

static void startup_complete(const struct innesto_mod_context *context, void *user_data)
{
    (void)user_data;
    report(context, "startup-complete");
}

int innesto_mod_init_v2(const struct innesto_mod_context *context)
{
    common = innesto_query_capability_v1(context, INNESTO_CAP_COMMON, 1);
    if (!common) {
        return 1;
    }
#ifdef EXAMPLE_SIDE_MODULE
    const struct innesto_environment_v1 *module =
        innesto_query_capability_v1(context, EXAMPLE_SIDE_MODULE, 1);
    if (!module || module->physical_environment != common->physical_environment(context)) {
        return 1;
    }
#endif
    report(context, "init");
    return common->on_startup_complete(context, startup_complete, NULL);
}
