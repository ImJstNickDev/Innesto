# Native mappings for a1.2.10

The private adapter maps semantic names to native functions and object types in
an exact build. Two original Linux x86-64 fixture executables implement the
cooperative interface. Both support a break rule and an inspect rule. A mapping
for the distributed game would require independently verified declarations and
its own trusted build record.

## Select a build and bind a rule

The adapter passes the observed game version, platform, physical process
environment and lowercase SHA-256 of the verified image to
`innesto_native_select`. Obtain the digest from the executable already
checked for launch. Maintain the expected digest independently in the mapping
profile. A missing profile yields `unavailable` and duplicate matching
profiles yield `ambiguous`.

Each profile associates semantic names with slots in its build's catalog.
A slot belongs to one native rule or one typed object projection. For example,
`block.break.permitted` selects a rule taking a live native object, while
`block.position` selects the function that returns its signed coordinates.
The two fixture builds reverse the break and inspect slots and store the
coordinates in different orders. Each projection reads its own concrete C
type. The host declares these slots directly to its adapter during startup.

Link the private `innesto-native-adapter` CMake target and include
`native_adapter.h` from adapter code. Provide a zero-initialized
`innesto_native_connection` at an address that stays valid while bound.

1. Select the profile and call `innesto_native_bind` with the profile, host
   catalog, semantic rule name, semantic type name, decision callback, callback
   context and connection. It checks uniqueness, signature, operand type,
   available implementations and site occupancy before publishing the connection.
2. Advertise the gameplay capability after binding succeeds. If the loader
   declines the capability, call `innesto_native_disconnect` during startup.
   Multiple distinct sites can use independent connections.
3. The host calls `innesto_native_call_rule` at the declared decision site.
   It runs the native rule once. A zero result stops there. For an allowed
   attempt, the projection builds a temporary coordinate snapshot and the
   connected callback runs. Zero from the callback vetoes the operation.
   A pass preserves the original return value, including positive values
   other than one. Mod listener ordering belongs to the event dispatcher.

`innesto_native_lookup` also resolves a single semantic name with an expected
kind. An absent name, slot or implementation yields `unavailable`. Duplicate
names or slot IDs yield `ambiguous`. Wrong kinds or operand types yield
`incompatible`. Retrying an occupied connection or site yields `occupied`.
Failed operations preserve the current binding. Bind and disconnect during
startup or after all callers have stopped. The host owns native object lifetime
through each call.

## Reproduce the fixture tests

Use a Linux x86-64 checkout with the native build prerequisites and binutils.
The default CTest run executes the original binaries after stripping them,
checks their ELF sections and dynamic symbol tables, and exercises different
profiles, signed snapshots, block removal, veto, pass, original return values, ordering and
independent sites. The builder records each reference hash after stripping.
The runner hashes the file it executes and supplies both inputs to the fixture.
It also runs a byte-modified copy under the original reference hashes and checks that the native rule remains available by itself.

```sh
cmake -S . -B build/native
cmake --build build/native --parallel
ctest --test-dir build/native --output-on-failure -R '^native-mappings$'
```

## Frida Gum evaluation

We evaluated Frida Gum 17.9.11 on Linux x86-64 against a separate original
executable. Its non-exported rule is known to the fixture by a direct function
reference. After stripping, Gum confirmed that export lookup could not find
the rule. Its Interceptor attached to that declared function and counted two
invocations. The original returned 7 and 0. After detaching, a third call
returned 7 and the listener count stayed at two. This tests attachment,
preservation of the original decision and detachment within the fixture
process. [Frida C API](https://frida.re/docs/c-api/) and
[Gum Interceptor](https://frida.re/docs/gum/class.Interceptor.html).

The cooperative backend serves the owned decision sites with ordinary C calls.
Their typed declarations provide the native rule and the object projection.
Gum's inline interception normally rewrites executable instructions and still
requires a known target with the correct native signature. The cooperative
backend avoids that executable-memory requirement and an additional runtime
dependency. Innesto's backend and original fixtures use the repository's MIT
license. Gum's own terms and component notices accompany its pinned release.
[Upstream license and notices](https://github.com/frida/frida-gum/blob/17.9.11/COPYING).

To repeat the optional evaluation, download the Linux x86-64
`frida-gum-devkit` archive from the pinned release. Save and check it before
extracting. CMake also checks the individual header and library hashes.
[Frida 17.9.11 release](https://github.com/frida/frida/releases/tag/17.9.11).

```sh
mkdir -p build/gum-devkit
curl -fsSL -o build/gum-devkit/devkit.tar.xz \
  https://github.com/frida/frida/releases/download/17.9.11/frida-gum-devkit-17.9.11-linux-x86_64.tar.xz
echo '33c82c9849c2d7d540e9995dc756dbed453dbf993af894fb15d963025de59dd8  build/gum-devkit/devkit.tar.xz' | sha256sum --check &&
  tar -xf build/gum-devkit/devkit.tar.xz -C build/gum-devkit ./frida-gum.h ./libfrida-gum.a
cmake -S . -B build/gum-probe -DINNESTO_GUM_DEVKIT="$PWD/build/gum-devkit"
cmake --build build/gum-probe --target innesto-gum-probe
ctest --test-dir build/gum-probe -V -R '^native-gum-probe$'
```

The native CI workflow also runs this check when a pull request changes the
Gum probe, its build rules or the workflow. Ordinary fixture tests build offline.
