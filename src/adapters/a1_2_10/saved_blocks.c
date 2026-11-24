#include "saved_blocks.h"
#include "runtime_adapter.h"
#include <innesto/saved_blocks.h>

#include <errno.h>
#include <fcntl.h>
#include <jansson.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* Configured once before mods initialize and immutable for the process lifetime. */
static int records_fd = -1;
static json_t *binding;
static const char *const field_names[] = {"revision", "player", "broken", "placed"};

static const char *text_field(json_t *object, const char *key)
{
    json_t *value = json_object_get(object, key);
    const char *text = json_string_value(value);
    return text && *text && strlen(text) == json_string_length(value) ? text : NULL;
}

static int load_object(int directory, const char *name, json_t **out)
{
    int fd = openat(directory, name, O_RDONLY | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW);
    if (fd < 0) {
        return errno == ENOENT ? INNESTO_SAVED_BLOCKS_NOT_FOUND : INNESTO_SAVED_BLOCKS_UNREADABLE;
    }

    FILE *stream = fdopen(fd, "r");
    if (!stream) {
        close(fd);
        return INNESTO_SAVED_BLOCKS_UNREADABLE;
    }
    struct stat before, after;
    int status = INNESTO_SAVED_BLOCKS_UNREADABLE;
    if (fstat(fd, &before) == 0 && S_ISREG(before.st_mode)) {
        json_error_t error;
        json_t *object = json_loadf(stream, JSON_REJECT_DUPLICATES, &error);
        if (!ferror(stream) && fstat(fd, &after) == 0 && before.st_size == after.st_size &&
            before.st_mtim.tv_sec == after.st_mtim.tv_sec &&
            before.st_mtim.tv_nsec == after.st_mtim.tv_nsec) {
            if (json_is_object(object)) {
                *out = object;
                status = INNESTO_SAVED_BLOCKS_OK;
            } else if (object || json_error_code(&error) != json_error_out_of_memory) {
                status = INNESTO_SAVED_BLOCKS_INVALID_RECORD;
            }
        }
        if (status != INNESTO_SAVED_BLOCKS_OK) {
            json_decref(object);
        }
    }
    fclose(stream);
    return status;
}

static int valid_uuid(const char *id)
{
    if (!id || strlen(id) != 36) {
        return 0;
    }
    for (size_t i = 0; i < 36; i++) {
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (id[i] != '-') {
                return 0;
            }
        } else if (!strchr("0123456789abcdef", id[i])) {
            return 0;
        }
    }
    return 1;
}

static int read_totals(const char *id, struct innesto_saved_block_totals_v1 *out)
{
    if (!valid_uuid(id) || !out) {
        return INNESTO_SAVED_BLOCKS_INVALID_ARGUMENT;
    }
    char name[sizeof "00000000-0000-0000-0000-000000000000.json"];
    snprintf(name, sizeof name, "%s.json", id);
    json_t *record = NULL;
    int status = load_object(records_fd, name, &record);
    if (status != INNESTO_SAVED_BLOCKS_OK) {
        return status;
    }

    json_t *fields = json_object_get(binding, "fields");
    json_t *revision = json_object_get(record, text_field(fields, "revision"));
    const char *owner = text_field(record, text_field(fields, "player"));
    json_t *broken = json_object_get(record, text_field(fields, "broken"));
    json_t *placed = json_object_get(record, text_field(fields, "placed"));
    if (!json_equal(revision, json_object_get(binding, "revision")) || !owner || strcmp(owner, id) ||
        !json_is_integer(broken) || json_integer_value(broken) < 0 ||
        !json_is_integer(placed) || json_integer_value(placed) < 0) {
        status = INNESTO_SAVED_BLOCKS_INVALID_RECORD;
    } else {
        *out = (struct innesto_saved_block_totals_v1){
            (uint64_t)json_integer_value(broken), (uint64_t)json_integer_value(placed)
        };
    }
    json_decref(record);
    return status;
}

static int valid_fields(json_t *fields)
{
    for (size_t i = 0; i < sizeof field_names / sizeof field_names[0]; i++) {
        const char *field = text_field(fields, field_names[i]);
        if (!field) {
            return 0;
        }
        for (size_t j = 0; j < i; j++) {
            if (strcmp(field, text_field(fields, field_names[j])) == 0) {
                return 0;
            }
        }
    }
    return 1;
}

void innesto_a1_2_10_activate_saved_blocks(const struct innesto_native_identity *observed,
                                          uint32_t physical)
{
    const char *path = getenv("INNESTO_SAVED_BLOCKS_BINDING");
    if (!path || physical != INNESTO_PHYSICAL_SERVER) {
        return;
    }
    json_t *config = NULL;
    if (*path != '/' || load_object(AT_FDCWD, path, &config) != INNESTO_SAVED_BLOCKS_OK) {
        fputs("Innesto: cannot read saved block totals binding\n", stderr);
        return;
    }
    const char *expected = text_field(config, "serverSha256");
    const char *directory = text_field(config, "directory");
    static const struct innesto_saved_blocks_v1 table = { read_totals };
    if (expected && strcmp(expected, observed->sha256) == 0 && directory && *directory == '/' &&
        json_is_integer(json_object_get(config, "revision")) &&
        valid_fields(json_object_get(config, "fields"))) {
        int fd = open(directory, O_RDONLY | O_CLOEXEC | O_DIRECTORY);
        if (fd >= 0) {
            if (faccessat(fd, ".", X_OK, AT_EACCESS) == 0 &&
                innesto_adapter_provide_v1(physical, INNESTO_CAP_SAVED_BLOCKS, 1, &table)) {
                records_fd = fd;
                binding = config;
                return;
            }
            close(fd);
        }
    }
    json_decref(config);
    fputs("Innesto: saved block totals binding unavailable\n", stderr);
}
