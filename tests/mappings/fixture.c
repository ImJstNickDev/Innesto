#include "fixture.h"
#include <stdio.h>

/* Two original layouts for the same semantic operation. Only this translation
 * unit knows how each host stores its object or reaches the native rule. */
#if FIXTURE_REVISION == 1
struct innesto_native_object {
    int present;
    int32_t x, y, z;
};
enum { BREAK = 31, INSPECT = 29, BLOCK = 17 };
static struct innesto_native_position owned_position(const struct innesto_native_object *object)
{
    return (struct innesto_native_position){object->x, object->y, object->z};
}
#else
struct innesto_native_object {
    int32_t zyx[3];
    long revision;
    int present;
};
enum { BREAK = 29, INSPECT = 31, BLOCK = 83 };
static struct innesto_native_position owned_position(const struct innesto_native_object *object)
{
    return (struct innesto_native_position){object->zyx[2], object->zyx[1], object->zyx[0]};
}
#endif

static int owned_break(const struct innesto_native_object *object)
{
    printf("original break %d\n", object->present);
    return object->present ? 7 : 0;
}

static int owned_inspect(const struct innesto_native_object *object)
{
    printf("original inspect %d\n", object->present);
    return object->present ? 11 : 0;
}

static struct innesto_native_site break_site = {.operand_slot = BLOCK, .original = owned_break};
static struct innesto_native_site inspect_site = {.operand_slot = BLOCK, .original = owned_inspect};

struct innesto_native_catalog owned_catalog(void)
{
    static const struct innesto_native_slot slots[] = {
        {INSPECT, INNESTO_NATIVE_RULE, {.rule = &inspect_site}},
        {BLOCK, INNESTO_NATIVE_POSITION, {.position = owned_position}},
        {BREAK, INNESTO_NATIVE_RULE, {.rule = &break_site}},
    };
    return (struct innesto_native_catalog){slots, sizeof(slots) / sizeof(slots[0])};
}

void owned_attempt(int inspect, int present, int32_t x, int32_t y, int32_t z)
{
#if FIXTURE_REVISION == 1
    struct innesto_native_object object = {.present = present, .x = x, .y = y, .z = z};
#else
    struct innesto_native_object object = {.zyx = {z, y, x}, .revision = 2, .present = present};
#endif
    int result = innesto_native_call_rule(inspect ? &inspect_site : &break_site, &object);
    printf("result %d\n", result);
    if (!inspect) {
        if (result) {
            object.present = 0;
        }
        printf("block present=%d\n", object.present);
    }
}
