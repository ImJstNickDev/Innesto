#include <innesto/runtime.h>
#include <innesto/saved_blocks.h>

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

int innesto_mod_init_v2(const struct innesto_mod_context *context)
{
    const struct innesto_saved_blocks_v1 *api =
        innesto_query_capability_v1(context, INNESTO_CAP_SAVED_BLOCKS, 1);
    puts(api ? "binding available" : "binding absent");
    fflush(stdout);
    char input[96];
    while (api && fgets(input, sizeof input, stdin)) {
        input[strcspn(input, "\n")] = '\0';
        struct innesto_saved_block_totals_v1 value = {22, 33};
        int status = api->read(strcmp(input, "null-id") == 0 ? NULL : input,
                               strcmp(input, "null-output") == 0 ? NULL : &value);
        printf("%d %" PRIu64 " %" PRIu64 "\n", status, value.broken, value.placed);
        fflush(stdout);
    }
    return 0;
}
