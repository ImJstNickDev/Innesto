#include "runtime.h"
#include "runtime_adapter.h"

#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

struct capability {
    uint32_t environment;
    const char *name;
    uint32_t version;
    const void *table;
    struct capability *next;
};

struct startup_listener {
    const struct innesto_mod_context *context;
    innesto_startup_complete_v1 callback;
    void *user_data;
    struct startup_listener *next;
};

static struct capability *capabilities;
static int capabilities_sealed;
static struct startup_listener *listeners;
static struct startup_listener **listener_tail = &listeners;
static _Thread_local const struct innesto_mod_context *initializing;
static _Thread_local uint32_t logical_side;
static atomic_int startup_finished;

static const struct innesto_environment_v1 client = { INNESTO_PHYSICAL_CLIENT };
static const struct innesto_environment_v1 server = { INNESTO_PHYSICAL_SERVER };

static const char *mod_id(const struct innesto_mod_context *context)
{
    return context->id;
}

static uint32_t physical_environment(const struct innesto_mod_context *context)
{
    return context->environment;
}

static uint32_t current_logical_side(void)
{
    return logical_side;
}

static int on_startup_complete(const struct innesto_mod_context *context,
                               innesto_startup_complete_v1 callback, void *user_data)
{
    if (!context || !callback) {
        return INNESTO_STARTUP_INVALID;
    }
    if (context != initializing) {
        return INNESTO_STARTUP_CLOSED;
    }
    struct startup_listener *item = malloc(sizeof *item);
    if (!item) {
        return INNESTO_STARTUP_NO_MEMORY;
    }
    *item = (struct startup_listener){ context, callback, user_data, NULL };
    *listener_tail = item;
    listener_tail = &item->next;
    return INNESTO_STARTUP_REGISTERED;
}

static const struct innesto_common_v1 common = {
    mod_id, physical_environment, current_logical_side, on_startup_complete
};

static const void *find_capability(uint32_t environment, const char *name, uint32_t version)
{
    for (struct capability *item = capabilities; item; item = item->next) {
        if (item->environment == environment && item->version == version &&
            strcmp(item->name, name) == 0) {
            return item->table;
        }
    }
    return NULL;
}

const void *innesto_query_capability_v1(const struct innesto_mod_context *context,
                                        const char *name, uint32_t version)
{
    if (!context || !name || !version) {
        return NULL;
    }
    if (version == 1) {
        if (strcmp(name, INNESTO_CAP_COMMON) == 0) {
            return &common;
        }
        if (context->environment == INNESTO_PHYSICAL_CLIENT && strcmp(name, INNESTO_CAP_CLIENT) == 0) {
            return &client;
        }
        if (context->environment == INNESTO_PHYSICAL_SERVER && strcmp(name, INNESTO_CAP_SERVER) == 0) {
            return &server;
        }
    }
    return find_capability(context->environment, name, version);
}

int innesto_adapter_provide_v1(uint32_t environment, const char *name,
                               uint32_t version, const void *table)
{
    if (capabilities_sealed || !name || !*name || !version || !table ||
        (environment != INNESTO_PHYSICAL_CLIENT && environment != INNESTO_PHYSICAL_SERVER) ||
        strcmp(name, INNESTO_CAP_COMMON) == 0 || strcmp(name, INNESTO_CAP_CLIENT) == 0 ||
        strcmp(name, INNESTO_CAP_SERVER) == 0 || find_capability(environment, name, version)) {
        return 0;
    }
    struct capability *item = malloc(sizeof *item);
    if (!item) {
        return 0;
    }
    *item = (struct capability){ environment, name, version, table, capabilities };
    capabilities = item;
    return 1;
}

void innesto_seal_capabilities(void)
{
    capabilities_sealed = 1;
}

int innesto_initialize_v2(const struct innesto_mod_context *context,
                          int (*initialize)(const struct innesto_mod_context *))
{
    initializing = context;
    int result = initialize(context);
    initializing = NULL;
    return result;
}

void innesto_finish_startup(void)
{
    for (struct startup_listener *item = listeners; item;) {
        struct startup_listener *next = item->next;
        item->callback(item->context, item->user_data);
        free(item);
        item = next;
    }
    listeners = NULL;
    listener_tail = &listeners;
    atomic_store(&startup_finished, 1);
}

int innesto_adapter_dispatch_v1(uint32_t side, void (*callback)(void *), void *data)
{
    if (!atomic_load(&startup_finished) || !callback ||
        (side != INNESTO_LOGICAL_CLIENT && side != INNESTO_LOGICAL_SERVER)) {
        return 0;
    }
    uint32_t previous = logical_side;
    logical_side = side;
    callback(data);
    logical_side = previous;
    return 1;
}
