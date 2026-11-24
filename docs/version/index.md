# Openworld a1.2.10

Innesto loads native mods at process startup on Linux x86-64. The dedicated
server has real-game acceptance. Original host fixtures exercise client and
server package selection.
Each mod has a manifest, an independently built shared library and a C
entrypoint. The loader validates the selected packages and initializes them
in dependency order before the host enters `main`.

- [Client, server and shared mods](environments.md) covers physical environments, capability discovery, logical sides and startup completion.
- [Build and load a mod package](mod-packages.md) to install the two example mods, write a manifest and declare dependencies.
- [Native mod initialization](native-initialization.md) describes the public C entrypoint, the private target profile and how to launch a single library.
