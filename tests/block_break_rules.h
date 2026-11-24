#ifndef FIXTURE_BLOCK_BREAK_RULES_H
#define FIXTURE_BLOCK_BREAK_RULES_H

#include <stdint.h>

struct fixture_block {
    int32_t x, y, z;
    int present;
    int drops;
};

int fixture_break_permitted(const struct fixture_block *block);

#endif
