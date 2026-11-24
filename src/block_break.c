#include "block_break_host.h"

#include <stdlib.h>

/* Only a host that implements the simulation contract supplies this function. */
extern void innesto_host_set_before_block_break_v1(innesto_before_block_break_v1 callback)
    __attribute__((weak, visibility("default")));

struct listener_entry {
    innesto_before_block_break_v1 call;
    struct listener_entry *next;
};

static struct listener_entry *first;
static struct listener_entry **next_slot = &first;
static _Thread_local int registering;

int innesto_register_before_block_break_v1(innesto_before_block_break_v1 listener)
{
    if (!listener) {
        return INNESTO_BREAK_INVALID;
    }
    if (!innesto_host_set_before_block_break_v1) {
        return INNESTO_BREAK_UNAVAILABLE;
    }
    if (!registering) {
        return INNESTO_BREAK_CLOSED;
    }

    struct listener_entry *entry = malloc(sizeof *entry);
    if (!entry) {
        return INNESTO_BREAK_NO_MEMORY;
    }
    entry->call = listener;
    entry->next = NULL;
    *next_slot = entry;
    next_slot = &entry->next;
    return INNESTO_BREAK_REGISTERED;
}

static int before_block_break(const struct innesto_block_break_v1 *attempt)
{
    for (const struct listener_entry *entry = first; entry; entry = entry->next) {
        if (entry->call(attempt) != INNESTO_BREAK_PASS) {
            return INNESTO_BREAK_VETO;
        }
    }
    return INNESTO_BREAK_PASS;
}

void innesto_block_break_open_registration(void)
{
    registering = 1;
}

void innesto_block_break_finish_registration(void)
{
    registering = 0;
    if (innesto_host_set_before_block_break_v1) {
        innesto_host_set_before_block_break_v1(before_block_break);
    }
}
