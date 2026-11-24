/* Original simulation fixture. The client here consumes the fixture's replies. */
#include "block_break_host.h"

#include <stdio.h>

static innesto_before_block_break_v1 before_break;

void innesto_host_set_before_block_break_v1(innesto_before_block_break_v1 callback)
{
    before_break = callback;
}

struct block {
    struct innesto_block_break_v1 position;
    int present;
    int drops;
};

struct client_view {
    int present;
    int successes;
    int corrections;
};

static void request_break(struct block *block, struct client_view *client)
{
    if (!block->present) {
        return;
    }

    /* A client predicts removal while the simulation still owns the block. */
    client->present = 0;
    if (before_break && before_break(&block->position) != INNESTO_BREAK_PASS) {
        client->present = block->present;
        client->corrections++;
        return;
    }

    block->present = 0;
    block->drops++;
    client->successes++;
}

static void print_state(const char *name, struct block block, struct client_view client)
{
    printf("%s world=%d drops=%d view=%d successes=%d corrections=%d\n",
           name, block.present, block.drops, client.present, client.successes, client.corrections);
}

int main(void)
{
    struct block first = {.position = {.x = 4, .y = 64, .z = -3}, .present = 1};
    struct block second = {.position = {.x = 0, .y = 65, .z = -7}, .present = 1};
    struct client_view first_view = {.present = 1};
    struct client_view second_view = {.present = 1};

    request_break(&first, &first_view);
    request_break(&first, &first_view); /* A stale retry cannot duplicate a drop. */
    request_break(&second, &second_view);
    print_state("first", first, first_view);
    print_state("second", second, second_view);
    return 0;
}
