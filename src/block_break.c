#include "block_break_adapter.h"
#include "runtime_adapter.h"

#include <stdatomic.h>
#include <stdlib.h>

enum adapter_state {
    AWAITING_ADAPTER,
    ADAPTER_ATTACHED,
    NO_ADAPTER,
    INACTIVE_BOOTSTRAP,
    DISPATCH_READY
};

static _Atomic enum adapter_state state = AWAITING_ADAPTER;

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
    enum adapter_state current = atomic_load(&state);
    if (current != ADAPTER_ATTACHED && current != DISPATCH_READY) {
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
    /* Publish the complete listener list before the first simulation call. */
    enum adapter_state current = atomic_load(&state);
    if (current == INACTIVE_BOOTSTRAP) {
        return INNESTO_BREAK_PASS;
    }
    if (current != DISPATCH_READY) {
        return INNESTO_BREAK_VETO;
    }
    for (const struct listener_entry *entry = first; entry; entry = entry->next) {
        if (entry->call(attempt) != INNESTO_BREAK_PASS) {
            return INNESTO_BREAK_VETO;
        }
    }
    return INNESTO_BREAK_PASS;
}

static const struct innesto_before_block_break_api_v1 block_break_api = {
    innesto_register_before_block_break_v1
};

int innesto_adapter_attach_before_block_break_v1(innesto_before_block_break_v1 *site, uint32_t physical)
{
    enum adapter_state expected = AWAITING_ADAPTER;
    if (!site || !atomic_compare_exchange_strong(&state, &expected, ADAPTER_ATTACHED)) {
        return 0;
    }
    if (!innesto_adapter_provide_v1(physical, INNESTO_CAP_BEFORE_BLOCK_BREAK, 1, &block_break_api)) {
        atomic_store(&state, NO_ADAPTER);
        return 0;
    }
    *site = before_block_break;
    return 1;
}

void innesto_block_break_bypass(void)
{
    atomic_store(&state, INACTIVE_BOOTSTRAP);
}

void innesto_block_break_seal_adapter(void)
{
    /* Mod libraries may execute constructors as soon as they are opened. */
    enum adapter_state expected = AWAITING_ADAPTER;
    atomic_compare_exchange_strong(&state, &expected, NO_ADAPTER);
}

void innesto_block_break_open_registration(void)
{
    registering = atomic_load(&state) == ADAPTER_ATTACHED;
}

void innesto_block_break_finish_registration(void)
{
    if (registering) {
        registering = 0;
        atomic_store(&state, DISPATCH_READY);
    }
}
