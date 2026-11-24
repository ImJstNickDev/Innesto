# Native mod initialization

The development branch for **Openworld a1.2.10 on Linux x86-64** can start
a local dedicated server with [installed mod packages](mod-packages.md) or
one explicitly selected library. The bootstrap calls each mod once during
process startup, before the server enters `main`. API 2 adds an opaque mod
context and a startup-complete notification for [client, server and shared
packages](environments.md).

## Build the loader and example

Use Linux x86-64 with glibc, a C11 compiler, CMake 3.18 or later, and Python
3.11 or later. In a checkout of the `game/a1.2.10` branch, run these commands
from the repository root.

```sh
cmake -S . -B build/native
cmake --build build/native
cmake -S examples/hello -B build/hello -DINNESTO_INCLUDE_DIR="$PWD/include"
cmake --build build/hello
ctest --test-dir build/native --output-on-failure
```

The example is a separate CMake project and needs only the public header to
compile. The tests launch an original fixture, match the mod's reported PID
to the host PID and check that the mod initializes once. This path also runs
in CI and requires no game installation.

## Write the entrypoint

An API 1 mod is a native shared library that exports this C function itself.
The single-library `--mod` command selects API 1 and takes no package ID.
Use `--mods-dir` and a manifest to select API 2.

```c
#include <innesto/mod.h>

int innesto_mod_init_v1(void)
{
    return 0;
}
```

The call runs synchronously on the startup thread. Returning zero allows
startup to continue. A missing entrypoint or a nonzero return stops
startup with an error. The library stays loaded for the lifetime of the
process. A native mod runs with the same permissions as the server, so select
a build you trust.

## Start a private target

A local maintainer profile is a JSON object with these fields.

| Field | Value |
| --- | --- |
| `version` | `a1.2.10` |
| `platform` | `linux-x86_64` |
| `executable` | Absolute path to the verified target executable |
| `sha256` | Expected SHA-256 of the executable from the verified reference package |
| `environment` | Optional physical environment, `client` or `server`. Defaults to `server` for existing profiles. |

Keep this profile private. Its digest pins the reference you trust. The
launcher checks the selected file against that value and executes the same
open file. Pass the bootstrap built with this checkout as `--loader` and keep
its generated `innesto-bootstrap.sha256` alongside it. The launcher verifies
this build artifact before starting the target.

From the checkout, with `profile` set to the absolute path of your private
profile and `run_dir` set to a dedicated server working directory, use the following invocation.

```sh
innesto_root=$(pwd -P)
(
  cd "$run_dir" || exit 1
  "$innesto_root/tools/innesto-run" \
    --profile "$profile" \
    --loader "$innesto_root/build/native/innesto-bootstrap.so" \
    --mod "$innesto_root/build/hello/innesto-hello.so" --
)
```

Use a library path free of literal glibc tokens such as `$ORIGIN` or `$LIB`.
Append the server's usual arguments after `--`. The example emits
`Innesto hello initialized (pid=N)` to standard error. Compare `N` with
the running server PID and check that the server reaches its ready state.
A normal launch of the server omits Innesto.

## Verified behavior

Two separate launches of the a1.2.10 dedicated server each emitted the
example marker once, in the verified server process. Both initialized fresh
worlds and shut down normally. A control launch emitted no marker. Changing
the expected fingerprint caused the launcher to reject the target before
starting the server. The [acceptance record](https://github.com/ImJstNickDev/Innesto/issues/1)
tracks the tested revision and results.
