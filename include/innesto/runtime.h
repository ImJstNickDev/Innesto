#ifndef INNESTO_RUNTIME_H
#define INNESTO_RUNTIME_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct innesto_mod_context;

/* Export this entrypoint for manifest api 2. The context belongs to the
 * loader and remains valid while the process is running. */
__attribute__((visibility("default")))
int innesto_mod_init_v2(const struct innesto_mod_context *context);

#define INNESTO_CAP_COMMON "innesto.common"
#define INNESTO_CAP_CLIENT "innesto.client"
#define INNESTO_CAP_SERVER "innesto.server"

/* Returns an immutable process-lifetime table, or NULL when unavailable.
 * Each (name, version) pair defines its own complete table layout. */
__attribute__((visibility("default")))
const void *innesto_query_capability_v1(const struct innesto_mod_context *context,
                                        const char *name, uint32_t version);

enum {
    INNESTO_PHYSICAL_CLIENT = 1,
    INNESTO_PHYSICAL_SERVER = 2
};
enum {
    INNESTO_LOGICAL_UNKNOWN = 0,
    INNESTO_LOGICAL_CLIENT = 1,
    INNESTO_LOGICAL_SERVER = 2
};

typedef void (*innesto_startup_complete_v1)(const struct innesto_mod_context *context,
                                            void *user_data);
enum {
    INNESTO_STARTUP_REGISTERED = 0,
    INNESTO_STARTUP_INVALID = 1,
    INNESTO_STARTUP_CLOSED = 2,
    INNESTO_STARTUP_NO_MEMORY = 3
};

struct innesto_common_v1 {
    const char *(*mod_id)(const struct innesto_mod_context *context);
    uint32_t (*physical_environment)(const struct innesto_mod_context *context);
    uint32_t (*logical_side)(void);
    int (*on_startup_complete)(const struct innesto_mod_context *context,
                               innesto_startup_complete_v1 callback, void *user_data);
};

/* Both physical modules have this v1 layout. Only the matching module is
 * available. Operational APIs use separate capability names and versions. */
struct innesto_environment_v1 {
    uint32_t physical_environment;
};

#ifdef __cplusplus
}
#endif

#endif
