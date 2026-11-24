/* Original simulation fixture. The client here consumes the fixture's replies. */
#include "block_break_rules.h"

#include <stdio.h>

struct client_view {
    int present;
    int successes;
    int corrections;
};

static void request_break(struct fixture_block *block, struct client_view *client)
{
    /* The client predicts removal before the simulation decides the request. */
    client->present = 0;
    if (!fixture_break_permitted(block)) {
        if (client->present != block->present) {
            client->present = block->present;
            client->corrections++;
        }
        return;
    }

    block->present = 0;
    block->drops++;
    client->successes++;
}

static void print_state(const char *name, struct fixture_block block, struct client_view client)
{
    printf("%s world=%d drops=%d view=%d successes=%d corrections=%d\n",
           name, block.present, block.drops, client.present, client.successes, client.corrections);
}

int main(void)
{
    struct fixture_block first = {.x = 4, .y = 64, .z = -3, .present = 1};
    struct fixture_block second = {.x = 0, .y = 65, .z = -7, .present = 1};
    struct client_view first_view = {.present = 1};
    struct client_view second_view = {.present = 1};

    request_break(&first, &first_view);
    request_break(&first, &first_view); /* A stale retry cannot duplicate a drop. */
    request_break(&second, &second_view);
    print_state("first", first, first_view);
    print_state("second", second, second_view);
    return 0;
}
