#include "simulation.h"
#ifdef INNESTO_SAVED_BLOCKS
#include "saved_blocks.h"
#endif

#include "block_break_adapter.h"
#include "runtime_adapter.h"

static const struct innesto_native_profile *records;
static size_t record_count;
static const struct innesto_native_catalog *sites;
static struct innesto_native_connection connection;
static innesto_before_block_break_v1 dispatch;
static int sealed;

int innesto_a1_2_10_offer_simulation(const struct innesto_native_profile *profiles,
                                    size_t count, const struct innesto_native_catalog *catalog)
{
    if (sealed || sites || !profiles || !count || !catalog) {
        return 0;
    }
    records = profiles;
    record_count = count;
    sites = catalog;
    return 1;
}

struct decision {
    struct innesto_block_break_v1 attempt;
    int result;
};

static void ask_listeners(void *data)
{
    struct decision *decision = data;
    decision->result = dispatch(&decision->attempt);
}

static int before_break(const struct innesto_native_position *position, void *context)
{
    (void)context;
    struct decision decision = {{position->x, position->y, position->z}, INNESTO_BREAK_VETO};
    innesto_adapter_dispatch_v1(INNESTO_LOGICAL_SERVER, ask_listeners, &decision);
    return decision.result == INNESTO_BREAK_PASS;
}

void innesto_a1_2_10_activate(const struct innesto_native_identity *observed, uint32_t physical)
{
    const struct innesto_native_profile *profile = NULL;
    sealed = 1;
#ifdef INNESTO_SAVED_BLOCKS
    innesto_a1_2_10_activate_saved_blocks(observed, physical);
#endif
    if (!sites || innesto_native_select(observed, records, record_count, &profile) != INNESTO_NATIVE_OK) {
        return;
    }
    if (innesto_native_bind(profile, sites, "block.break.permitted", "block.position",
                            before_break, NULL, &connection) != INNESTO_NATIVE_OK) {
        return;
    }
    if (!innesto_adapter_attach_before_block_break_v1(&dispatch, physical)) {
        innesto_native_disconnect(&connection);
    }
}
