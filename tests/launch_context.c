/* Observe the process at the earliest point at which this mod can execute. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <innesto/mod.h>

__attribute__((constructor)) static void check_launch_context(void)
{
    const char *expected_fds = getenv("TEST_INNESTO_FDS");
    const char *preload = getenv("LD_PRELOAD");
    int loader, list;
    if (!expected_fds || sscanf(expected_fds, "%d %d", &loader, &list) != 2 ||
        !preload || strcmp(preload, "") != 0 ||
        getenv("INNESTO_LOADER_FD") || getenv("INNESTO_MOD_LIST_FD") ||
        getenv("INNESTO_INIT_PID") || getenv("INNESTO_MOD_PATH") ||
        getenv("INNESTO_PREVIOUS_PRELOAD")) {
        _Exit(93);
    }
    if (fcntl(loader, F_GETFD) != -1 || errno != EBADF ||
        fcntl(list, F_GETFD) != -1 || errno != EBADF) {
        _Exit(94);
    }
}

int innesto_mod_init_v1(void)
{
    return 0;
}
