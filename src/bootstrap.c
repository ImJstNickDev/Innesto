#define _GNU_SOURCE

#include "block_break_adapter.h"

#include <dlfcn.h>
#include <limits.h>
#include <link.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct mod {
    char *path;
    int (*initialize)(void);
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

static struct mod *consume_launch_context(void)
{
    int loader = inherited_fd("INNESTO_LOADER_FD");
    int list = inherited_fd("INNESTO_MOD_LIST_FD");
    if (loader == list) {
        startup_error("loader and mod list require separate descriptors");
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
    struct mod *mods = NULL;
    struct mod **tail = &mods;
    for (;;) {
        char *path = NULL;
        size_t capacity = 0;
        ssize_t length = getdelim(&path, &capacity, '\0', paths);
        if (length < 0) {
            free(path);
            if (ferror(paths) || !feof(paths)) {
                startup_error("could not read mod list");
            }
            break;
        }
        if (path[0] != '/' || path[length - 1] != '\0') {
            startup_error("mod list requires NUL-terminated absolute paths");
        }
        struct mod *entry = calloc(1, sizeof *entry);
        if (!entry) {
            startup_error("could not allocate mod list");
        }
        entry->path = path;
        *tail = entry;
        tail = &entry->next;
    }
    if (fclose(paths) != 0) {
        startup_error("could not close mod list descriptor");
    }
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
    void *symbol = dlsym(mod, "innesto_mod_init_v1");
    if (dlerror() || !symbol) {
        mod_error(entry->path, "mod entrypoint innesto_mod_init_v1 is missing");
    }
    // dlsym also searches dependencies and can return a data object.
    struct link_map *module_map;
    Dl_info info;
    void *metadata;
    if (dlinfo(mod, RTLD_DI_LINKMAP, &module_map) != 0 ||
        !dladdr1(symbol, &info, &metadata, RTLD_DL_SYMENT) || !metadata ||
        strcmp(info.dli_fname, module_map->l_name) != 0 ||
        ELF64_ST_TYPE(((const ElfW(Sym) *)metadata)->st_info) != STT_FUNC) {
        mod_error(entry->path, "mod must export innesto_mod_init_v1 as its own function");
    }

    _Static_assert(sizeof entry->initialize == sizeof symbol, "expected POSIX function pointers");
    memcpy(&entry->initialize, &symbol, sizeof symbol);
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

    struct mod *mods = consume_launch_context();
    innesto_block_break_seal_adapter();
    for (struct mod *entry = mods; entry; entry = entry->next) {
        resolve_entrypoint(entry);
    }
    innesto_block_break_open_registration();
    while (mods) {
        int result = mods->initialize();
        if (result != 0) {
            dprintf(STDERR_FILENO, "Innesto: %s: mod initialization failed (returned %d)\n",
                    mods->path, result);
            _Exit(EXIT_FAILURE);
        }
        struct mod *next = mods->next;
        free(mods->path);
        free(mods);
        mods = next;
    }
    innesto_block_break_finish_registration();
}
