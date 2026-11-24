#include <innesto/block_break.h>
#include "block_break_host.h"

#include <stddef.h>
#include <stdio.h>

static innesto_before_block_break_v1 before_break;
static int calls;
static int error;

void innesto_host_set_before_block_break_v1(innesto_before_block_break_v1 listener)
{
    before_break = listener;
}

static int pass(const struct innesto_block_break_v1 *attempt)
{
    if (attempt->x != -1 || attempt->y != 0 || attempt->z != 8 || calls != 0) {
        error = 1;
    }
    ++calls;
    return INNESTO_BREAK_PASS;
}

static int unknown_result(const struct innesto_block_break_v1 *attempt)
{
    (void)attempt;
    if (calls != 1 || innesto_register_before_block_break_v1(pass) != INNESTO_BREAK_CLOSED) {
        error = 1;
    }
    ++calls;
    return 37;
}

int main(void)
{
    const struct innesto_block_break_v1 attempt = {-1, 0, 8};
    if (innesto_register_before_block_break_v1(pass) != INNESTO_BREAK_CLOSED) {
        return 1;
    }
    innesto_block_break_open_registration();
    if (innesto_register_before_block_break_v1(NULL) != INNESTO_BREAK_INVALID ||
        innesto_register_before_block_break_v1(pass) != INNESTO_BREAK_REGISTERED ||
        innesto_register_before_block_break_v1(unknown_result) != INNESTO_BREAK_REGISTERED ||
        innesto_register_before_block_break_v1(pass) != INNESTO_BREAK_REGISTERED || before_break) {
        return 1;
    }
    innesto_block_break_finish_registration();
    if (before_break == NULL || before_break(&attempt) != INNESTO_BREAK_VETO || calls != 2 || error) {
        fputs("dispatch did not stop at the first non-pass result\n", stderr);
        return 1;
    }
    return 0;
}
