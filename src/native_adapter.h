#ifndef INNESTO_NATIVE_ADAPTER_H
#define INNESTO_NATIVE_ADAPTER_H

/* Private C11 contract for cooperative, in-process target adapters. */
#include <stddef.h>
#include <stdint.h>

struct innesto_native_identity {
    const char *version;
    const char *platform;
    const char *environment;
    const char *sha256; /* Lowercase SHA-256 of the checked image. */
};

enum innesto_native_status {
    INNESTO_NATIVE_OK,
    INNESTO_NATIVE_UNAVAILABLE,
    INNESTO_NATIVE_AMBIGUOUS,
    INNESTO_NATIVE_INCOMPATIBLE,
    INNESTO_NATIVE_INVALID,
    INNESTO_NATIVE_OCCUPIED
};

struct innesto_native_name {
    const char *semantic;
    unsigned slot;
};

struct innesto_native_profile {
    struct innesto_native_identity identity;
    const struct innesto_native_name *names;
    size_t name_count;
};

/* The owner defines the concrete native object and its typed projection. */
struct innesto_native_object;
struct innesto_native_position {
    int32_t x, y, z;
};
typedef int (*innesto_native_rule)(const struct innesto_native_object *);
typedef struct innesto_native_position (*innesto_native_project)(const struct innesto_native_object *);
/* Return nonzero to retain the original decision, zero to veto it. */
typedef int (*innesto_native_before)(const struct innesto_native_position *, void *);

struct innesto_native_connection;
struct innesto_native_site {
    unsigned operand_slot;
    innesto_native_rule original;
    const struct innesto_native_connection *active;
};

enum innesto_native_kind { INNESTO_NATIVE_RULE, INNESTO_NATIVE_POSITION };
struct innesto_native_slot {
    unsigned id;
    enum innesto_native_kind kind;
    union {
        struct innesto_native_site *rule;
        innesto_native_project position;
    } value;
};

struct innesto_native_catalog {
    const struct innesto_native_slot *slots;
    size_t count;
};

struct innesto_native_connection {
    struct innesto_native_site *site;
    innesto_native_project project;
    innesto_native_before before;
    void *context;
};

/* Output arguments are written only on success. Catalogs are trusted, typed
 * declarations. The caller obtains observed identity from its verified launch. */
enum innesto_native_status innesto_native_select(const struct innesto_native_identity *observed,
    const struct innesto_native_profile *profiles,
    size_t count,
    const struct innesto_native_profile **out);

enum innesto_native_status innesto_native_lookup(const struct innesto_native_profile *profile,
    const struct innesto_native_catalog *catalog,
    const char *semantic,
    enum innesto_native_kind expected,
    const struct innesto_native_slot **out);

/* Bind/disconnect at startup or once callers are quiescent. The caller supplies
 * a zero-initialized connection at a stable address for the entire binding. */
enum innesto_native_status innesto_native_bind(const struct innesto_native_profile *profile,
    const struct innesto_native_catalog *catalog,
    const char *rule_name,
    const char *type_name,
    innesto_native_before before,
    void *context,
    struct innesto_native_connection *connection);
void innesto_native_disconnect(struct innesto_native_connection *connection);

/* The owner calls its initialized site with a live operand of the declared type. */
int innesto_native_call_rule(
    const struct innesto_native_site *site, const struct innesto_native_object *object);
const char *innesto_native_status_name(enum innesto_native_status status);

#endif
