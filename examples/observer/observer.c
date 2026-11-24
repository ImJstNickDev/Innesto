#include <innesto/mod.h>
#include <stdio.h>
#include <unistd.h>

int innesto_mod_init_v1(void)
{
    return fprintf(stderr, "Innesto observer initialized (pid=%ld)\n", (long)getpid()) < 0;
}
