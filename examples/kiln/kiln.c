#include <innesto/mod.h>
#include <stdio.h>

int innesto_mod_init_v1(void)
{
    return fputs("Innesto kiln initialized\n", stderr) == EOF;
}
