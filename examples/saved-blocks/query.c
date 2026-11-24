#include <innesto/runtime.h>
#include <innesto/saved_blocks.h>

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

int innesto_mod_init_v2(const struct innesto_mod_context *context)
{
    const struct innesto_saved_blocks_v1 *api =
        innesto_query_capability_v1(context, INNESTO_CAP_SAVED_BLOCKS, 1);
    if (!api) {
        fputs("saved-blocks: capability unavailable\n", stderr);
        return 0;
    }
    const char *player = getenv("INNESTO_EXAMPLE_PLAYER_UUID");
    if (!player) {
        fputs("saved-blocks: set INNESTO_EXAMPLE_PLAYER_UUID to read a player\n", stderr);
        return 0;
    }
    struct innesto_saved_block_totals_v1 totals;
    int status = api->read(player, &totals);
    if (status == INNESTO_SAVED_BLOCKS_OK) {
        fprintf(stderr, "saved-blocks: broken=%" PRIu64 " placed=%" PRIu64 "\n",
                totals.broken, totals.placed);
    } else {
        fprintf(stderr, "saved-blocks: query status %d\n", status);
    }
    return 0;
}
