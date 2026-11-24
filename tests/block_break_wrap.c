#include "fixture_break_adapter.h"
#include "block_break_rules.h"

/* Linux runs an executable's preinit array before shared-library constructors.
 * Only the link that wraps the rule installs the event site. */
__attribute__((used, section(".preinit_array")))
static void (*const install_adapter)(void) = fixture_install_break_adapter;

/* The fixture's adapted build resolves this call to the original rule. */
int __real_fixture_break_permitted(const struct fixture_block *block);

int __wrap_fixture_break_permitted(const struct fixture_block *block)
{
    return __real_fixture_break_permitted(block) &&
           fixture_dispatch_break(block->x, block->y, block->z);
}
