#include <innesto/block_break.h>
#include "block_break_adapter.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

static innesto_before_block_break_v1 before_break;
static int calls;
static int error;

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

static int check_unattached(void)
{
    innesto_before_block_break_v1 site = pass;
    if (innesto_adapter_attach_before_block_break_v1(NULL) != 0) {
        fputs("null site unexpectedly attached\n", stderr);
        return 1;
    }
    innesto_block_break_seal_adapter();
    if (innesto_adapter_attach_before_block_break_v1(&site) != 0 || site != pass) {
        fputs("adapter attached during mod library discovery\n", stderr);
        return 1;
    }
    innesto_block_break_open_registration();
    if (innesto_adapter_attach_before_block_break_v1(&site) != 0 || site != pass ||
        innesto_register_before_block_break_v1(pass) != INNESTO_BREAK_UNAVAILABLE) {
        fputs("missing adapter was accepted during initialization\n", stderr);
        return 1;
    }
    innesto_block_break_finish_registration();
    return innesto_adapter_attach_before_block_break_v1(&site) != 0 || site != pass ||
           innesto_register_before_block_break_v1(pass) != INNESTO_BREAK_UNAVAILABLE;
}

int main(int argc, char **argv)
{
    const struct innesto_block_break_v1 attempt = {-1, 0, 8};
    innesto_before_block_break_v1 second_site = unknown_result;
    if (argc == 2 && strcmp(argv[1], "unattached") == 0) {
        return check_unattached();
    } else if (argc != 1) {
        return 2;
    }
    if (innesto_adapter_attach_before_block_break_v1(&before_break) != 1 || !before_break ||
        innesto_adapter_attach_before_block_break_v1(&second_site) != 0 || second_site != unknown_result ||
        innesto_register_before_block_break_v1(pass) != INNESTO_BREAK_CLOSED ||
        before_break(&attempt) != INNESTO_BREAK_VETO || calls != 0) {
        fputs("attachment must succeed only once before initialization\n", stderr);
        return 1;
    }
    innesto_block_break_seal_adapter();
    innesto_block_break_open_registration();
    if (innesto_register_before_block_break_v1(NULL) != INNESTO_BREAK_INVALID ||
        innesto_register_before_block_break_v1(pass) != INNESTO_BREAK_REGISTERED ||
        before_break(&attempt) != INNESTO_BREAK_VETO || calls != 0 ||
        innesto_register_before_block_break_v1(unknown_result) != INNESTO_BREAK_REGISTERED ||
        innesto_register_before_block_break_v1(pass) != INNESTO_BREAK_REGISTERED) {
        return 1;
    }
    innesto_block_break_finish_registration();
    if (before_break(&attempt) != INNESTO_BREAK_VETO || calls != 2 || error) {
        fputs("dispatch did not stop at the first non-pass result\n", stderr);
        return 1;
    }
    return 0;
}
