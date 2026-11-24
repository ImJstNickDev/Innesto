# Openworld a1.2.10

Innesto loads native mods at process startup on Linux x86-64. Each mod has a manifest, an independently built shared library and a C
entrypoint. The loader validates the selected packages and initializes them
in dependency order before the host enters `main`.

- [Client, server and shared mods](environments.md) covers physical environments, capability discovery, logical sides and startup completion.
- [Build and load a mod package](mod-packages.md) to install the two example mods, write a manifest and declare dependencies.
- [Native mod initialization](native-initialization.md) describes the public C entrypoint, the private target profile and how to launch a single library.
- [Terrain materials](terrain-materials.md) covers shared asset packages, direct connections and world compatibility.
- [Saved block totals](saved-block-totals.md) lets server mods read persisted player progress.
- [Native mappings](native-mappings.md) describes exact-build function and type resolution, typed decision hooks, and the original stripped fixtures.

## Verified behavior

| Target | Observed behavior |
| --- | --- |
| Openworld dedicated server | API 1 and API 2 examples initialized together. A saved world reopened after package removal and reinstallation. See the [server restart check](mod-packages.md#check-a-dedicated-server-restart). |
| Openworld client | The shared and client hello packages initialized and completed startup before the menu. The dedicated-server package was skipped. The client reopened the menu after removal. [Offline client check](environments.md#offline-client-bootstrap) |
| Openworld terrain packages | Two independent packages placed terrain on the dedicated server. Both original textures rendered in a connected client, and reopening the same world with reversed package folders preserved the terrain. [Install the examples](terrain-materials.md) |
| Innesto's stripped simulation fixtures | The [before-block-break capability](before-block-break.md) dispatches on the logical server in both dedicated and integrated configurations. A veto preserves the modeled block and suppresses its drop. |

[Issue #3](https://github.com/ImJstNickDev/Innesto/issues/3) tracks the
decision and player-visible veto in the distributed game. It gates the
[first development release](https://github.com/ImJstNickDev/Innesto/milestone/1).
