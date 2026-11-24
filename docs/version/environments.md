# Client, server and shared mods

The physical environment identifies the executable selected by a private
target profile. A dedicated server profile uses `"environment": "server"`.
A client profile uses `"environment": "client"`. Profiles written
before this field existed default to `server`. The profile owner identifies
the process and pins its fingerprint. A mod declares which processes can
load its library in its manifest.

| Manifest environment | Physical client | Dedicated server |
| --- | --- | --- |
| `client` | Loads | Skipped |
| `server` | Skipped | Loads |
| `shared` | Loads | Loads |

A shared package has one ID, version and library. Its dependencies must be
present on every physical environment where you intend to use it. A
client-only or server-only package can depend on a shared package. If an
active mod requires a mod filtered out for this launch, the launcher reports
both IDs and the physical environment and exits before starting the host.

## Try the three packages

From the repository root, build the original host and the three public example
packages. This example needs Linux x86-64 with glibc.

```sh
cmake -S . -B build/native
cmake --build build/native
cmake -S examples/environments -B build/environments -DINNESTO_INCLUDE_DIR="$PWD/include"
cmake --build build/environments
cmake --install build/environments --prefix "$PWD/build/side-packages"
ctest --test-dir build/native -R 'environments|runtime-contract' --output-on-failure
```

To see the markers yourself, prepare two profiles pointing at the same
original host fixture. Its digest binds both profiles to this local build.

```sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path

host = Path("build/native/innesto-test-host").resolve()
for side in ("client", "server"):
    profile = {"version": "a1.2.10", "platform": "linux-x86_64", "environment": side,
               "executable": str(host), "sha256": hashlib.sha256(host.read_bytes()).hexdigest()}
    Path(f"build/{side}-fixture.json").write_text(json.dumps(profile))
PY

for side in client server; do
  tools/innesto-run --profile "build/$side-fixture.json" \
    --loader build/native/innesto-bootstrap.so --mods-dir build/side-packages
done
```

For each launch, `shared-hello` initializes first, then `client-hello` or
`server-hello`. Each writes a second marker during startup completion.
All four markers have the host's PID and `logical=unknown`. Removing the
environment-specific package leaves both markers from `shared-hello`.
The commands above exercise the original test host on both profiles.

## Offline client bootstrap

The three `examples/environments` packages were built separately from the
loader and tested with the distributed a1.2.10 Linux x86-64 client. The
local run used a verified, read-only installation, an isolated display
and a network namespace with only loopback. Each hello mod queried
Innesto's capability tables and reported its own lifecycle. The test
ended at the main menu.

| Launch | Observed inside the client PID |
| --- | --- |
| Ordinary startup | The client displayed its menu with zero hello markers. |
| All three packages installed | `shared-hello` initialized before `client-hello`. Startup-complete ran in the same order. Both libraries were mapped in the client process. `server-hello` was skipped. |
| Packages removed, loader retained | The client displayed its menu again with zero hello libraries and zero markers. |

All four callbacks in the middle run reported physical `client` and
logical `unknown` before the menu appeared. Each run shut down cleanly
from the menu. Gameplay callbacks and an integrated world each require
their own acceptance test. [Client acceptance record](https://github.com/ImJstNickDev/Innesto/issues/28).

## Get the mod context

Package API 2 first appears on the a1.2.10 development branch for Linux
x86-64. To port an API 1 mod, change the manifest's `api` field to `2`,
include `innesto/runtime.h` and export `innesto_mod_init_v2`. The following
shared mod reports its package ID once all selected mods have initialized.

```c
#include <innesto/runtime.h>
#include <stdio.h>

static void started(const struct innesto_mod_context *ctx, void *data)
{
    (void)data;
    const struct innesto_common_v1 *common =
        innesto_query_capability_v1(ctx, INNESTO_CAP_COMMON, 1);
    fprintf(stderr, "%s completed startup\n", common->mod_id(ctx));
}

int innesto_mod_init_v2(const struct innesto_mod_context *ctx)
{
    const struct innesto_common_v1 *common =
        innesto_query_capability_v1(ctx, INNESTO_CAP_COMMON, 1);
    return common ? common->on_startup_complete(ctx, started, NULL) : 1;
}
```

Innesto owns the opaque context, its mod ID string and the immutable capability
tables. A mod can retain those pointers for the lifetime of the process. Pass
your own context to APIs that take one. The loader calls the initializer once
on the startup thread. Returning nonzero aborts startup before host `main`.

## Discover modules

`innesto_query_capability_v1(ctx, name, version)` looks up an exact table
version. An unknown name, unavailable module or unsupported version returns
`NULL`. Check the result before using optional functionality.

| Module and version | Table | Availability and operations |
| --- | --- | --- |
| `innesto.common`, 1 | `struct innesto_common_v1` | Both processes. Read the manifest ID, physical environment and current logical side, or register a startup-complete callback. |
| `innesto.client`, 1 | `struct innesto_environment_v1` | Physical client. Its `physical_environment` field is `INNESTO_PHYSICAL_CLIENT`. |
| `innesto.server`, 1 | `struct innesto_environment_v1` | Dedicated server. Its `physical_environment` field is `INNESTO_PHYSICAL_SERVER`. |

The matching physical module identifies where the mod is running. Gameplay
capabilities require their own lookup and a verified adapter that supplies
the implementation for that process.

## Startup completion

`common->on_startup_complete(ctx, callback, user_data)` accepts registrations
during that mod's initializer on its startup thread. It returns
`INNESTO_STARTUP_REGISTERED` on success. Null contexts or callbacks return
`INNESTO_STARTUP_INVALID`, registrations outside that window return
`INNESTO_STARTUP_CLOSED`, and allocation failure returns
`INNESTO_STARTUP_NO_MEMORY`.

After the last successful initializer and before host `main`, Innesto closes
registration and invokes every registered callback once on the startup thread
in registration order. Each receives its mod context and its original user
pointer. Keep any pointed-to data alive through that call. With zero
registrations, startup proceeds directly to the host. A failed initializer
suppresses all completion callbacks. A completion callback returns `void`.
World or rendering readiness requires a separate verified host callback.

## Physical environment and logical side

`common->physical_environment(ctx)` stays constant for the process.
`common->logical_side()` describes the current callback on the calling
thread. Startup, startup completion and unclassified work return
`INNESTO_LOGICAL_UNKNOWN` on both physical environments.

A version adapter can establish `INNESTO_LOGICAL_CLIENT` or
`INNESTO_LOGICAL_SERVER` around a callback where the host role is known.
For example, a verified integrated simulation callback can report logical
server while the process remains a physical client. Nested dispatch restores
the outer role on return, and other threads keep their own roles. Loading a
client profile alone establishes neither integrated simulation nor gameplay
event availability. The contract test uses an original adapter fixture to
exercise these transitions.
