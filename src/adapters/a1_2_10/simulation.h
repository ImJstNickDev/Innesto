#ifndef INNESTO_A1_2_10_SIMULATION_H
#define INNESTO_A1_2_10_SIMULATION_H

#include "native_adapter.h"

/* Adapter-owned descriptions must outlive the process. Registration precedes
 * the bootstrap constructor. Selection uses the launcher's verified image. */
__attribute__((visibility("default")))
int innesto_a1_2_10_offer_simulation(const struct innesto_native_profile *profiles,
                                    size_t count, const struct innesto_native_catalog *catalog);

/* Called by the bootstrap before any mod library is opened. */
void innesto_a1_2_10_activate(const struct innesto_native_identity *observed, uint32_t physical);
#endif
