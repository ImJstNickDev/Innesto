#ifndef INNESTO_RUNTIME_ADAPTER_H
#define INNESTO_RUNTIME_ADAPTER_H

#include <innesto/runtime.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Adapter-only interfaces. Publish after attaching the actual implementation,
 * during serial host setup before the bootstrap resolves any mod. All strings
 * and tables supplied by an adapter must live for the entire process.
 * Returns 1 on success, 0 for invalid, duplicate, or late publications. */
__attribute__((visibility("default")))
int innesto_adapter_provide_v1(uint32_t physical_environment, const char *name,
                               uint32_t version, const void *table);

/* Invoke on the calling thread with a verified logical role. Restores the
 * enclosing role after a normal return. Valid after startup-complete.
 * Returns 1 if invoked, 0 for invalid arguments or early dispatch. */
__attribute__((visibility("default")))
int innesto_adapter_dispatch_v1(uint32_t logical_side, void (*callback)(void *), void *data);

#ifdef __cplusplus
}
#endif

#endif
