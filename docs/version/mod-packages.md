# Build and load a mod package

Innesto discovers native mods in a directory you select with
`--mods-dir`. Each installed mod occupies one subdirectory containing
`innesto.mod.json` and its library. The manifest gives the mod its identity,
declares what it needs and points to the library that exports its entrypoint.

## Try two mods

From the root of a `game/a1.2.10` checkout on Linux x86-64, build the loader
and install both examples in a fresh package directory. You need glibc, Python
3.11 or later, CMake 3.18 or later and a C11 compiler. The two mods are
separate CMake projects. Each compiles against Innesto's public header.

```sh
cmake -S . -B build/native
cmake --build build/native

for mod in hello observer; do
  cmake -S "examples/$mod" -B "build/$mod" -DINNESTO_INCLUDE_DIR="$PWD/include"
  cmake --build "build/$mod"
  cmake --install "build/$mod" --prefix "$PWD/build/packages"
done
ctest --test-dir build/native --output-on-failure
```

The tests exercise the launcher with an original host fixture. To use your
local dedicated server, set `profile` to the absolute path of its
[private target profile](native-initialization.md#start-a-private-target) and
`run_dir` to the server working directory.

```sh
innesto_root=$(pwd -P)
(
  cd "$run_dir" || exit 1
  "$innesto_root/tools/innesto-run" \
    --profile "$profile" \
    --loader "$innesto_root/build/native/innesto-bootstrap.so" \
    --mods-dir "$innesto_root/build/packages" --
)
```

The examples each write one line to standard error. Both lines report the
server PID. `hello` appears first because `observer` depends on it. To disable
`observer`, move its package directory outside `build/packages` and restart.
An empty package directory starts the server with zero mods. The
[single-library command](native-initialization.md#start-a-private-target)
remains available for testing an individual build.

## Check a dedicated server restart

Start with the `hello` and `observer` installation above. Build the
[environment examples](environments.md) and install them into the same
package directory.

```sh
cmake -S examples/environments -B build/environments -DINNESTO_INCLUDE_DIR="$PWD/include"
cmake --build build/environments
cmake --install build/environments --prefix "$PWD/build/packages"
```

Use a private copy of a stopped world and the same server profile and data
directory for each launch. Expect the following markers on the dedicated server.

| Phase | Packages, in order |
| --- | --- |
| API 1 initialization | `hello`, `observer` |
| API 2 initialization | `shared-hello`, `server-hello` |
| API 2 startup completion | `shared-hello`, `server-hello` |

All six markers carry the server PID and precede readiness. The installed
`client-hello` package emits zero markers. Stop the server normally, move
`observer` outside the package directory, and restart. Five markers should
appear. An empty package directory produces zero. Restoring the original
packages and restarting restores all six markers.

These steps passed on the distributed a1.2.10 Linux x86-64 dedicated
server. Requiring the unavailable [block-break event](before-block-break.md)
stopped the launch before the server listened. Removing that requirement
allowed startup packages to open the same saved world again.

## Write a manifest

Here is the installed `observer/innesto.mod.json`.

```json
{
  "schemaVersion": 1,
  "id": "observer",
  "version": "1.0.0",
  "game": "a1.2.10",
  "api": 1,
  "environment": "server",
  "entrypoint": "innesto-observer.so",
  "depends": {
    "hello": "*"
  }
}
```

| Field | Value in schema 1 |
| --- | --- |
| `schemaVersion` | Integer `1` selects this manifest format. |
| `id` | Unique ID starting with a lowercase ASCII letter. The remaining characters may also include digits, underscores and hyphens. Dependencies refer to this ID regardless of the directory name. |
| `version` | Three dot-separated decimal integers, such as `1.0.0`. Each component uses a single zero or starts with a nonzero digit. |
| `game` | Exact game version, `"a1.2.10"`. |
| `api` | Integer `1` selects the original C entrypoint. Integer `2` selects the [context entrypoint](environments.md#get-the-mod-context). |
| `environment` | `"client"`, `"server"` or `"shared"` selects eligible [physical environments](environments.md). |
| `entrypoint` | Relative path to a regular shared library inside the package. Paths may use subdirectories and must stay inside the package without any `..` components. The library must export its own [C initialization function](native-initialization.md#write-the-entrypoint). |
| `content` | Optional [terrain content registration](terrain-materials.md) for a shared mod. |
| `depends` | Optional object mapping required mod IDs to `"*"` (any installed version) or an exact version such as `"1.0.0"`. |

Use one manifest per immediate subdirectory. Every field except `depends` and `content` is
required. Loose files at the top level are ignored. Unknown manifest fields
and duplicate JSON keys are errors. Choose installation paths without literal
dynamic linker tokens such as `$ORIGIN`, `$LIB` or `${PLATFORM}`. Those tokens
have special meaning to glibc even inside an absolute library path.

## Initialization and errors

The launcher checks manifest syntax, game/API compatibility, relative path
syntax and unique IDs across the directory. It then selects packages for the
profile’s physical environment. It resolves files, dependency versions and
cycles only for the selected graph. An active dependency on a skipped
package stops startup. Inactive packages may omit their library on disk.
Each physical file may appear only once in the selected set.

Innesto initializes dependencies first. When several mods are ready, it calls
the one with the lexicographically smallest ID. Before calling an
initializer, it opens all selected libraries and resolves every
entrypoint. Keep initialization in that function. Native library constructors
can run as soon as the system linker opens a library.

If an entrypoint returns nonzero, startup stops immediately. Earlier callbacks
may already have run. All active mods share the host process and its permissions.
