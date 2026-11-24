#include "fixture.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static int before(const struct innesto_native_position *position, void *context)
{
    const char *action = context;
    printf("%s position %" PRId32 ",%" PRId32 ",%" PRId32 "\n",
        action,
        position->x,
        position->y,
        position->z);
    return !strcmp(action, "inspect") || position->x != 0;
}

int main(int argc, char **argv)
{
    if (argc != 5) {
        return 1;
    }
    /* Test caller supplies independent build reference digests and the actual
     * file digest. Production launchers check identity on the open executable. */
    const char *scenario = argv[4];
    struct innesto_native_name rev1[] = {
        {"block.break.permitted", 31}, {"block.position", 17}, {"block.inspect.permitted", 29},
    };
    struct innesto_native_name rev2[] = {
        {"block.position", 83}, {"block.inspect.permitted", 31}, {"block.break.permitted", 29},
    };
    struct innesto_native_profile profiles[] = {
        {{"a1.2.10", "linux-x86_64", "server", argv[2]}, rev2, 3},
        {{"a1.2.10", "linux-x86_64", "server", argv[1]}, rev1, 3},
    };
    struct innesto_native_identity observed = {"a1.2.10", "linux-x86_64", "server", argv[3]};
    const struct innesto_native_catalog declared = owned_catalog();
    struct innesto_native_slot slots[4] = {0};
    memcpy(slots, declared.slots, declared.count * sizeof(*slots));
    struct innesto_native_catalog catalog = {slots, declared.count};

    if (!strcmp(scenario, "version")) {
        observed.version = "a1.2.11";
    }
    if (!strcmp(scenario, "platform")) {
        observed.platform = "linux-arm64";
    }
    if (!strcmp(scenario, "environment")) {
        observed.environment = "client";
    }
    if (!strcmp(scenario, "digest")) {
        observed.sha256 = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee";
    }
    if (!strcmp(scenario, "malformed-digest")) {
        observed.sha256 = "unverified";
    }
    if (!strcmp(scenario, "profile-twice")) {
        profiles[0].identity = profiles[1].identity = observed;
    }
    if (!strcmp(scenario, "name-twice")) {
        rev1[2] = rev1[0];
        rev2[1] = rev2[2];
    }
    if (!strcmp(scenario, "slot-twice")) {
        slots[catalog.count++] = slots[2];
    }
    struct innesto_native_site unavailable_rule = {0};
    if (!strcmp(scenario, "missing-original")) {
        slots[2].value.rule = &unavailable_rule;
    }
    if (!strcmp(scenario, "wrong-kind")) {
        slots[2].kind = INNESTO_NATIVE_POSITION;
    }
    if (!strcmp(scenario, "wrong-operand")) {
        slots[2].value.rule->operand_slot = 999;
    }
    if (!strcmp(scenario, "missing-projector")) {
        slots[1].value.position = NULL;
    }

    const char *rule = !strcmp(scenario, "missing-function") ? "absent" : "block.break.permitted";
    const char *type = !strcmp(scenario, "missing-type") ? "absent" : "block.position";
    const struct innesto_native_profile *profile = NULL;
    struct innesto_native_connection connection = {0}, second = {0};
    enum innesto_native_status status = innesto_native_select(&observed, profiles, 2, &profile);
    if (status == INNESTO_NATIVE_OK) {
        status = innesto_native_bind(profile, &catalog, rule, type, before, "break", &connection);
    }
    printf("setup %s\n", innesto_native_status_name(status));
    if (status != INNESTO_NATIVE_OK) {
        owned_attempt(0, 1, -4, 71, 9);
        return 0;
    }
    status = innesto_native_bind(profile, &catalog, rule, type, before, "inspect", &second);
    printf("busy %s\n", innesto_native_status_name(status));
    status = innesto_native_bind(profile, &catalog, "block.inspect.permitted", type, before, "inspect", &second);
    if (status != INNESTO_NATIVE_OK) {
        return 1;
    }
    owned_attempt(0, 1, -4, 71, 9);
    owned_attempt(0, 1, 0, -20, 63);
    owned_attempt(0, 0, 4, 0, 0);
    owned_attempt(1, 1, 0, -20, 63);
    innesto_native_disconnect(&connection);
    owned_attempt(0, 1, 0, -20, 63);
    innesto_native_disconnect(&second);
    return 0;
}
