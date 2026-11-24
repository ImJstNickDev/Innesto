/* Consume an Innesto fixture profile through the existing typed native adapter. */
#include "fixture.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int before(const struct innesto_native_position *pos, void *context)
{
    (void)context;
    printf("reviewed %" PRId32 " %" PRId32 " %" PRId32 "\n", pos->x, pos->y, pos->z);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 1) {
        owned_attempt(0, 1, 4, 5, 6);
        return 0;
    }
    if (argc != 8 || strcmp(argv[1], "dedicated") != 0) {
        return 1;
    }
    struct innesto_native_name names[] = {
        {argv[4], (unsigned)strtoul(argv[5], NULL, 10)}, {argv[6], (unsigned)strtoul(argv[7], NULL, 10)}
    };
    struct innesto_native_profile profile = {{"a1.2.10", "linux-x86_64", "server", argv[2]}, names, 2};
    struct innesto_native_identity launched = {"a1.2.10", "linux-x86_64", "server", argv[3]};
    const struct innesto_native_profile *selected = NULL;
    struct innesto_native_catalog catalog = owned_catalog();
    struct innesto_native_connection connection = {0};
    if (innesto_native_select(&launched, &profile, 1, &selected) != INNESTO_NATIVE_OK ||
        innesto_native_bind(selected, &catalog, argv[4], argv[6], before, NULL, &connection) != INNESTO_NATIVE_OK) {
        return 2;
    }
    owned_attempt(0, 1, 4, 5, 6);
    innesto_native_disconnect(&connection);
    return 0;
}
