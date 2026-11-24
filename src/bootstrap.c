#define _GNU_SOURCE

#include "runtime.h"
#include "block_break_adapter.h"
#include "adapters/a1_2_10/simulation.h"

#include <dlfcn.h>
#include <fcntl.h>
#include <limits.h>
#include <link.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct mod {
    char *path;
    struct innesto_mod_context context;
    int api;
    union {
        int (*v1)(void);
        int (*v2)(const struct innesto_mod_context *);
    } initialize;
    struct mod *next;
};

static _Noreturn void startup_error(const char *message)
{
    dprintf(STDERR_FILENO, "Innesto: %s\n", message);
    _Exit(EXIT_FAILURE);
}

static _Noreturn void mod_error(const char *path, const char *message)
{
    dprintf(STDERR_FILENO, "Innesto: %s: %s\n", path, message);
    _Exit(EXIT_FAILURE);
}

static int inherited_fd(const char *name)
{
    const char *value = getenv(name);
    if (value && *value >= '0' && *value <= '9') {
        char *end;
        long fd = strtol(value, &end, 10);
        if (*end == '\0' && fd >= 3 && fd <= INT_MAX) {
            return (int)fd;
        }
    }
    dprintf(STDERR_FILENO, "Innesto: missing or invalid file descriptor in %s\n", name);
    _Exit(EXIT_FAILURE);
}

/* EOF can end a plan only between complete records. */
static char *plan_field(FILE *stream, int allow_eof)
{
    char *value = NULL;
    size_t capacity = 0;
    ssize_t length = getdelim(&value, &capacity, '\0', stream);
    if (length < 0) {
        free(value);
        if (allow_eof && feof(stream) && !ferror(stream)) {
            return NULL;
        }
        startup_error("incomplete mod plan");
    }
    if (value[length - 1] != '\0') {
        startup_error("mod plan requires NUL-terminated fields");
    }
    return value;
}

static struct mod *consume_launch_context(void)
{
    int loader = inherited_fd("INNESTO_LOADER_FD");
    int list = inherited_fd("INNESTO_MOD_LIST_FD");
    if (loader == list) {
        startup_error("loader and mod list require separate descriptors");
    }
    if (getenv("INNESTO_WORLD_LEASE_FD")) {
        int lease = inherited_fd("INNESTO_WORLD_LEASE_FD");
        // Keep the lease in this game even if its launcher exits. An exec'd
        // helper must not retain it after the game itself stops.
        if (lease == loader || lease == list || fcntl(lease, F_SETFD, FD_CLOEXEC) < 0) {
            startup_error("invalid world lease descriptor");
        }
        unsetenv("INNESTO_WORLD_LEASE_FD");
    }

    // Restore the caller's preload environment before dlopen can run constructors.
    const char *previous = getenv("INNESTO_PREVIOUS_PRELOAD");
    if (previous) {
        if (setenv("LD_PRELOAD", previous, 1) < 0) {
            startup_error("could not restore preload environment");
        }
    } else {
        unsetenv("LD_PRELOAD");
    }
    unsetenv("INNESTO_INIT_PID");
    unsetenv("INNESTO_MOD_LIST_FD");
    unsetenv("INNESTO_MOD_PATH");
    unsetenv("INNESTO_LOADER_FD");
    unsetenv("INNESTO_PREVIOUS_PRELOAD");
    if (close(loader) != 0) {
        startup_error("could not close loader file descriptor");
    }

    FILE *paths = fdopen(list, "rb");
    if (!paths) {
        startup_error("could not open mod list descriptor");
    }
    char *format = plan_field(paths, 0);
    if (strcmp(format, "Innesto/3") != 0) {
        startup_error("unknown mod plan format");
    }
    free(format);
    char *side = plan_field(paths, 0);
    uint32_t environment;
    if (strcmp(side, "server") == 0) {
        environment = INNESTO_PHYSICAL_SERVER;
    } else if (strcmp(side, "client") == 0) {
        environment = INNESTO_PHYSICAL_CLIENT;
    } else {
        startup_error("invalid physical environment in mod plan");
    }
    char *digest = plan_field(paths, 0);
    if (strlen(digest) != 64 || strspn(digest, "0123456789abcdef") != 64) {
        startup_error("invalid executable identity in mod plan");
    }

    struct mod *mods = NULL;
    struct mod **tail = &mods;
    char *api;
    while ((api = plan_field(paths, 1))) {
        struct mod *entry = calloc(1, sizeof *entry);
        if (!entry) {
            startup_error("could not allocate mod list");
        }
        if (strcmp(api, "1") == 0) {
            entry->api = 1;
        } else if (strcmp(api, "2") == 0) {
            entry->api = 2;
        } else {
            startup_error("invalid mod API in plan");
        }
        free(api);
        entry->context.environment = environment;
        char *id = plan_field(paths, 0);
        if (*id) {
            if (*id < 'a' || *id > 'z' ||
                id[strspn(id, "abcdefghijklmnopqrstuvwxyz0123456789_-")] != '\0') {
                startup_error("invalid mod ID in plan");
            }
            entry->context.id = id;
        } else {
            free(id);
            if (entry->api != 1) {
                startup_error("context entrypoint requires a packaged mod ID");
            }
        }
        entry->path = plan_field(paths, 0);
        if (entry->path[0] != '/') {
            startup_error("mod plan requires absolute paths");
        }
        *tail = entry;
        tail = &entry->next;
    }
    if (fclose(paths) != 0) {
        startup_error("could not close mod list descriptor");
    }
    const struct innesto_native_identity identity = {"a1.2.10", "linux-x86_64", side, digest};
    innesto_a1_2_10_activate(&identity, environment);
    free(side);
    free(digest);
    return mods;
}

static void resolve_entrypoint(struct mod *entry)
{
    // Retain the dlopen reference until process exit so mod code remains callable.
    void *mod = dlopen(entry->path, RTLD_NOW | RTLD_LOCAL);
    if (!mod) {
        mod_error(entry->path, dlerror());
    }

    dlerror();
    const char *name = entry->api == 1 ? "innesto_mod_init_v1" : "innesto_mod_init_v2";
    void *symbol = dlsym(mod, name);
    if (dlerror() || !symbol) {
        dprintf(STDERR_FILENO, "Innesto: %s: mod entrypoint %s is missing\n", entry->path, name);
        _Exit(EXIT_FAILURE);
    }
    // dlsym also searches dependencies and can return a data object.
    struct link_map *module_map;
    Dl_info info;
    void *metadata;
    if (dlinfo(mod, RTLD_DI_LINKMAP, &module_map) != 0 ||
        !dladdr1(symbol, &info, &metadata, RTLD_DL_SYMENT) || !metadata ||
        strcmp(info.dli_fname, module_map->l_name) != 0 ||
        ELF64_ST_TYPE(((const ElfW(Sym) *)metadata)->st_info) != STT_FUNC) {
        mod_error(entry->path, "mod must export its selected entrypoint as its own function");
    }

    _Static_assert(sizeof entry->initialize.v1 == sizeof symbol &&
                   sizeof entry->initialize.v2 == sizeof symbol, "expected POSIX function pointers");
    if (entry->api == 1) {
        memcpy(&entry->initialize.v1, &symbol, sizeof symbol);
    } else {
        memcpy(&entry->initialize.v2, &symbol, sizeof symbol);
    }
}

__attribute__((constructor)) static void initialize_mods(void)
{
    const char *launch_pid = getenv("INNESTO_INIT_PID");
    char current_pid[32];
    snprintf(current_pid, sizeof current_pid, "%ld", (long)getpid());
    if (!launch_pid || strcmp(launch_pid, current_pid) != 0) {
        innesto_block_break_bypass();
        return;
    }

    static struct mod *mods;  // Contexts passed to v2 mods live until process exit.
    mods = consume_launch_context();
    innesto_block_break_seal_adapter();
    innesto_seal_capabilities();
    for (struct mod *entry = mods; entry; entry = entry->next) {
        resolve_entrypoint(entry);
    }
    innesto_block_break_open_registration();
    for (struct mod *entry = mods; entry; entry = entry->next) {
        int result = entry->api == 1 ? entry->initialize.v1() :
            innesto_initialize_v2(&entry->context, entry->initialize.v2);
        if (result != 0) {
            dprintf(STDERR_FILENO, "Innesto: %s: mod initialization failed (returned %d)\n",
                    entry->path, result);
            _Exit(EXIT_FAILURE);
        }
    }
    innesto_block_break_finish_registration();
    innesto_finish_startup();
}
