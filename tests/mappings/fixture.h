#ifndef INNESTO_MAPPING_FIXTURE_H
#define INNESTO_MAPPING_FIXTURE_H

#include "native_adapter.h"

struct innesto_native_catalog owned_catalog(void);
void owned_attempt(int inspect, int present, int32_t x, int32_t y, int32_t z);

#endif
