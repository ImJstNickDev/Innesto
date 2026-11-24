#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    printf("host pid=%ld\n", (long)getpid());
    printf("preload=%s\n", getenv("LD_PRELOAD") ? getenv("LD_PRELOAD") : "");
    for (int i = 1; i < argc; i++) {
        printf("argument=%s\n", argv[i]);
    }
    fflush(stdout);
    if (getenv("INNESTO_INIT_PID") || getenv("INNESTO_MOD_PATH") ||
        getenv("INNESTO_PREVIOUS_PRELOAD") || getenv("INNESTO_LOADER_FD")) {
        return 91;
    }
    if (argc == 2 && strcmp(argv[1], "--reexec") == 0) {
        execl("/proc/self/exe", argv[0], "child", (char *)NULL);
        return 92;
    }
    return 0;
}
