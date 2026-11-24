// Original deterministic inputs for the research-tool checks.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef VARIANT
#error define VARIANT for each fixture image
#endif

#if VARIANT == 7
#define TONE_ALIGNMENT 16
#else
#define TONE_ALIGNMENT 128
#endif

__attribute__((noinline, aligned(TONE_ALIGNMENT)))
static uint32_t tone(uint32_t x) {
    for (unsigned i = 0; i < 5; i++) {
        x = (x ^ (x >> 9)) * 33U + i;
    }
    return x;
}

__attribute__((noinline))
static uint32_t limit(uint32_t x) {
    if (x < 23U) {
        return x * 3U + VARIANT;
    }
    return (x >> 2) ^ 55U;
}

__attribute__((noinline))
static uint32_t count_bits(uint32_t x) {
    uint32_t result = 0;
    while (x) {
        result++;
        x &= x - 1;
    }
    return result;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        return 1;
    }
    uint32_t x = (uint32_t)strtoul(argv[1], NULL, 0);
    printf("%u %u %u\n", tone(x), limit(x), count_bits(x));
    return 0;
}
