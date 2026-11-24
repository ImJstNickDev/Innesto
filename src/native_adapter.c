#include "native_adapter.h"

#include <string.h>

static int valid_identity(const struct innesto_native_identity *id)
{
    return id && id->version && *id->version && id->platform && *id->platform && id->environment &&
           *id->environment && id->sha256 && strlen(id->sha256) == 64 &&
           strspn(id->sha256, "0123456789abcdef") == 64;
}

enum innesto_native_status innesto_native_select(const struct innesto_native_identity *observed,
    const struct innesto_native_profile *profiles,
    size_t count,
    const struct innesto_native_profile **out)
{
    if (!valid_identity(observed) || (count && !profiles) || !out) {
        return INNESTO_NATIVE_INVALID;
    }
    const struct innesto_native_profile *match = NULL;
    for (size_t i = 0; i < count; ++i) {
        const struct innesto_native_identity *id = &profiles[i].identity;
        if (!valid_identity(id)) {
            return INNESTO_NATIVE_INVALID;
        }
        if (strcmp(id->version, observed->version) || strcmp(id->platform, observed->platform) ||
            strcmp(id->environment, observed->environment) || strcmp(id->sha256, observed->sha256)) {
            continue;
        }
        if (match) {
            return INNESTO_NATIVE_AMBIGUOUS;
        }
        match = &profiles[i];
    }
    if (!match) {
        return INNESTO_NATIVE_UNAVAILABLE;
    }
    *out = match;
    return INNESTO_NATIVE_OK;
}

enum innesto_native_status innesto_native_lookup(const struct innesto_native_profile *profile,
    const struct innesto_native_catalog *catalog,
    const char *semantic,
    enum innesto_native_kind expected,
    const struct innesto_native_slot **out)
{
    if (!profile || (profile->name_count && !profile->names) || !catalog ||
        (catalog->count && !catalog->slots) || !semantic || !*semantic || !out) {
        return INNESTO_NATIVE_INVALID;
    }
    const struct innesto_native_name *entry = NULL;
    for (size_t i = 0; i < profile->name_count; ++i) {
        const struct innesto_native_name *name = &profile->names[i];
        if (!name->semantic || !*name->semantic) {
            return INNESTO_NATIVE_INVALID;
        }
        if (strcmp(name->semantic, semantic) != 0) {
            continue;
        }
        if (entry) {
            return INNESTO_NATIVE_AMBIGUOUS;
        }
        entry = name;
    }
    if (!entry) {
        return INNESTO_NATIVE_UNAVAILABLE;
    }
    const struct innesto_native_slot *slot = NULL;
    for (size_t i = 0; i < catalog->count; ++i) {
        if (catalog->slots[i].id != entry->slot) {
            continue;
        }
        if (slot) {
            return INNESTO_NATIVE_AMBIGUOUS;
        }
        slot = &catalog->slots[i];
    }
    if (!slot) {
        return INNESTO_NATIVE_UNAVAILABLE;
    }
    if (slot->kind != expected) {
        return INNESTO_NATIVE_INCOMPATIBLE;
    }
    switch (expected) {
    case INNESTO_NATIVE_RULE:
        if (!slot->value.rule || !slot->value.rule->original) {
            return INNESTO_NATIVE_UNAVAILABLE;
        }
        break;
    case INNESTO_NATIVE_POSITION:
        if (!slot->value.position) {
            return INNESTO_NATIVE_UNAVAILABLE;
        }
        break;
    default:
        return INNESTO_NATIVE_INVALID;
    }
    *out = slot;
    return INNESTO_NATIVE_OK;
}

enum innesto_native_status innesto_native_bind(const struct innesto_native_profile *profile,
    const struct innesto_native_catalog *catalog,
    const char *rule_name,
    const char *type_name,
    innesto_native_before before,
    void *context,
    struct innesto_native_connection *connection)
{
    if (!before || !connection) {
        return INNESTO_NATIVE_INVALID;
    }
    if (connection->site) {
        return INNESTO_NATIVE_OCCUPIED;
    }

    const struct innesto_native_slot *rule, *type;
    enum innesto_native_status status =
        innesto_native_lookup(profile, catalog, rule_name, INNESTO_NATIVE_RULE, &rule);
    if (status != INNESTO_NATIVE_OK) {
        return status;
    }
    status = innesto_native_lookup(profile, catalog, type_name, INNESTO_NATIVE_POSITION, &type);
    if (status != INNESTO_NATIVE_OK) {
        return status;
    }
    struct innesto_native_site *site = rule->value.rule;
    if (site->operand_slot != type->id) {
        return INNESTO_NATIVE_INCOMPATIBLE;
    }
    if (site->active) {
        return INNESTO_NATIVE_OCCUPIED;
    }
    *connection = (struct innesto_native_connection){site, type->value.position, before, context};
    site->active = connection;
    return INNESTO_NATIVE_OK;
}

void innesto_native_disconnect(struct innesto_native_connection *connection)
{
    if (connection && connection->site && connection->site->active == connection) {
        connection->site->active = NULL;
        *connection = (struct innesto_native_connection){0};
    }
}

int innesto_native_call_rule(
    const struct innesto_native_site *site, const struct innesto_native_object *object)
{
    int decision = site->original(object);
    const struct innesto_native_connection *active = site->active;
    if (decision && active) {
        struct innesto_native_position position = active->project(object);
        if (!active->before(&position, active->context)) {
            return 0;
        }
    }
    return decision;
}

const char *innesto_native_status_name(enum innesto_native_status status)
{
    switch (status) {
    case INNESTO_NATIVE_OK:
        return "ok";
    case INNESTO_NATIVE_UNAVAILABLE:
        return "unavailable";
    case INNESTO_NATIVE_AMBIGUOUS:
        return "ambiguous";
    case INNESTO_NATIVE_INCOMPATIBLE:
        return "incompatible";
    case INNESTO_NATIVE_INVALID:
        return "invalid";
    case INNESTO_NATIVE_OCCUPIED:
        return "occupied";
    }
    return "unknown";
}
