# Openworld a1.2.10

Innesto loads native mods at process startup on Linux x86-64. Each mod has a manifest, an independently built shared library and a C
entrypoint. The loader validates the selected packages and initializes them
in dependency order before the host enters `main`.

- [Client, server and shared mods](environments.md) covers physical environments, capability discovery, logical sides and startup completion.
- [Build and load a mod package](mod-packages.md) to install the two example mods, write a manifest and declare dependencies.
- [Native mod initialization](native-initialization.md) describes the public C entrypoint, the private target profile and how to launch a single library.
- [Native mappings](native-mappings.md) describes exact-build function and type resolution, typed decision hooks, and the original stripped fixtures.

## Verified behavior

| Target | Observed behavior |
| --- | --- |
| Openworld dedicated server | API 1 and API 2 examples initialized together. A saved world reopened after package removal and reinstallation. See the [server restart check](mod-packages.md#check-a-dedicated-server-restart). |
| Original Openworld client | The unmodified client reached the menu in an isolated offline run. Client mod initialization has been exercised on the original Innesto fixtures. |
| Innesto's stripped simulation fixtures | The [before-block-break capability](before-block-break.md) dispatches on the logical server in both dedicated and integrated configurations. A veto preserves the modeled block and suppresses its drop. |

Innesto's client mod tests use original fixtures. The game's terms restrict
use of a modified client. [Openworld terms of use, section 6](https://www.play-openworld.com/legal/en/conditions).

[Issue #3](https://github.com/ImJstNickDev/Innesto/issues/3) tracks the
decision and player-visible veto in the distributed game. It gates the
[first development release](https://github.com/ImJstNickDev/Innesto/milestone/1).
