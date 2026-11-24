/* Original small ELF with two co-occurring literals and a single-literal decoy. */
#include <stdio.h>

__attribute__((noinline)) int record_pair(FILE *stream)
{
    int first = fputs("fixture_cobalt", stream);
    int second = fputs("fixture_amber", stream);
    return first < 0 || second < 0;
}

__attribute__((noinline)) int record_one(FILE *stream)
{
    return fputs("fixture_cobalt", stream);
}

int main(int argc, char **argv)
{
    (void)argv;
    return argc > 1 ? record_one(stdout) : record_pair(stdout);
}
