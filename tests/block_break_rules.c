#include "block_break_rules.h"

int fixture_break_permitted(const struct fixture_block *block)
{
    return block->present;
}
