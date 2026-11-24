#define _GNU_SOURCE

#include <dlfcn.h>
#include <limits.h>
#include <link.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static _Noreturn void startup_error(const char *message)
{
    dprintf(STDERR_FILENO, "Innesto: %s\n", message);
    _Exit(EXIT_FAILURE);
}

static int loader_fd(void)
{
    const char *value = getenv("INNESTO_LOADER_FD");
    char *end;
    if (!value || *value < '0' || *value > '9') {
        startup_error("missing loader file descriptor");
    }

    long fd = strtol(value, &end, 10);
    if (*end != '\0' || fd < 3 || fd > INT_MAX) {
        startup_error("invalid loader file descriptor");
    }

    return (int)fd;
}

static char *consume_launch_context(void)
{
    const char *path = getenv("INNESTO_MOD_PATH");
    if (!path || *path != '/') {
        startup_error("expected an absolute mod path");
    }
    char *mod_path = strdup(path);
    if (!mod_path) {
        startup_error("could not retain mod path");
    }

    // Restore the caller's preload environment before any mod code can run.
    int fd = loader_fd();
    const char *previous = getenv("INNESTO_PREVIOUS_PRELOAD");
    if (previous) {
        if (setenv("LD_PRELOAD", previous, 1) < 0) {
            startup_error("could not restore preload environment");
        }
    } else {
        unsetenv("LD_PRELOAD");
    }
    unsetenv("INNESTO_INIT_PID");
    unsetenv("INNESTO_MOD_PATH");
    unsetenv("INNESTO_LOADER_FD");
    unsetenv("INNESTO_PREVIOUS_PRELOAD");
    if (close(fd) != 0) {
        startup_error("could not release loader file descriptor");
    }

    return mod_path;
}

__attribute__((constructor)) static void initialize_mod(void)
{
    const char *launch_pid = getenv("INNESTO_INIT_PID");
    char current_pid[32];
    snprintf(current_pid, sizeof current_pid, "%ld", (long)getpid());
    if (!launch_pid || strcmp(launch_pid, current_pid) != 0) {
        return;
    }

    char *path = consume_launch_context();
    void *mod = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    free(path);
    if (!mod) {
        startup_error(dlerror());
    }

    dlerror();
    void *symbol = dlsym(mod, "innesto_mod_init_v1");
    if (dlerror() || !symbol) {
        startup_error("mod entrypoint innesto_mod_init_v1 is missing");
    }
    // dlsym also searches dependencies and can return a data object.
    struct link_map *module_map;
    Dl_info info;
    void *metadata;
    if (dlinfo(mod, RTLD_DI_LINKMAP, &module_map) != 0 ||
        !dladdr1(symbol, &info, &metadata, RTLD_DL_SYMENT) || !metadata ||
        strcmp(info.dli_fname, module_map->l_name) != 0 ||
        ELF64_ST_TYPE(((const ElfW(Sym) *)metadata)->st_info) != STT_FUNC) {
        startup_error("mod must export innesto_mod_init_v1 as its own function");
    }

    int (*initialize)(void);
    _Static_assert(sizeof initialize == sizeof symbol, "expected POSIX function pointers");
    memcpy(&initialize, &symbol, sizeof initialize);
    if (initialize() != 0) {
        startup_error("mod initialization failed");
    }
    // Keep the dlopen reference until process exit so mod code remains callable.
}
