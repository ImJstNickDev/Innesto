#include <innesto/mod.h>
#include <stdio.h>
#include <unistd.h>

int innesto_mod_init_v1(void)
{
    return fprintf(stderr, "Innesto hello initialized (pid=%ld)\n", (long)getpid()) < 0;
}
