#include "adapters/a1_2_10/simulation.h"
#include "block_break_rules.h"

#include <stdio.h>

extern int innesto_a1_2_10_offer_simulation(const struct innesto_native_profile *, size_t,
                                             const struct innesto_native_catalog *) __attribute__((weak));
int __real_fixture_break_permitted(const struct fixture_block *block);

struct innesto_native_object { const struct fixture_block *block; };

static int original_rule(const struct innesto_native_object *object)
{
    return __real_fixture_break_permitted(object->block);
}

static struct innesto_native_position coordinates(const struct innesto_native_object *object)
{
    const struct fixture_block *block = object->block;
    return (struct innesto_native_position){block->x, block->y, block->z};
}

enum { RULE = 1, POSITION = 2 };
static struct innesto_native_site rule = {POSITION, original_rule, NULL};
static const struct innesto_native_slot slots[] = {
    {RULE, INNESTO_NATIVE_RULE, {.rule = &rule}},
    {POSITION, INNESTO_NATIVE_POSITION, {.position = coordinates}},
};
static const struct innesto_native_catalog catalog = {slots, 2};
static const struct innesto_native_name names[] = {
    {"block.break.permitted", RULE}, {"block.position", POSITION},
};
static char digest[65];
static const struct innesto_native_profile profile = {
    {"a1.2.10", "linux-x86_64", FIXTURE_ENVIRONMENT, digest}, names, 2,
};

static void offer_fixture(void)
{
    if (!innesto_a1_2_10_offer_simulation) {
        return;
    }
    /* CMake records these original fixture bytes at build time, after stripping.
     * A different image at launch must not become a match by hashing itself. */
    FILE *stamp = fopen(FIXTURE_STAMP, "rb");
    if (stamp) {
        size_t length = fread(digest, 1, sizeof digest - 1, stamp);
        int trailer = fgetc(stamp);
        if (length == sizeof digest - 1 && trailer == '\n' && fgetc(stamp) == EOF && !ferror(stamp)) {
            innesto_a1_2_10_offer_simulation(&profile, 1, &catalog);
        }
        fclose(stamp);
    }
}

__attribute__((used, section(".preinit_array")))
static void (*const install_adapter)(void) = offer_fixture;

int __wrap_fixture_break_permitted(const struct fixture_block *block)
{
    const struct innesto_native_object object = {block};
    return innesto_native_call_rule(&rule, &object);
}
