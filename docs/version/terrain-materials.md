# Terrain materials

A shared native package can register a named terrain material and its texture when Innesto launches a dedicated server or a client joining it. A material can be placed by the server's terrain editing tools. Inventory stacks, crafting recipes, custom block behavior and solo worlds have separate requirements.

## Package a texture

The following field is part of the `copperfield` example's `innesto.mod.json`. The mod keeps its native entrypoint and sets `environment` to `shared`.

```json
"content": {
  "version": 1,
  "assets": "assets",
  "terrain": [
    { "id": "copperfield:ochre", "texture": "ochre.png" }
  ]
}
```

Put the original image at `assets/ochre.png` in the package. Version 1 takes non-interlaced 32 × 32 RGBA PNGs with eight bits per channel, up to 64 KiB. Export the image with only its header, image data and end chunks. Both paths must resolve inside their respective package and asset directories. The namespace is the mod ID. The local name also starts with a lowercase ASCII letter and can contain lowercase letters, digits, underscores and hyphens. Duplicate IDs, collisions with stock materials and names too long for the local adapter fail startup.

The registration contract is declarative and runs before native initialization. Mod authors use the namespaced ID in the package. For operator placement, use the material name shown by the running dedicated server's dashboard. Numeric material slots belong to the world and depend on its pinned base catalogue.

## Install both examples

From a Linux x86-64 checkout of `game/a1.2.10`, build each mod independently and install the two resulting package directories on both peers.

```sh
cmake -S . -B build/native
cmake --build build/native
for mod in copperfield tidepool; do
  cmake -S "examples/$mod" -B "build/$mod" -DINNESTO_INCLUDE_DIR="$PWD/include"
  cmake --build "build/$mod"
  cmake --install "build/$mod" --prefix "$PWD/build/terrain-mods"
done
```

This installs `copperfield:ochre` and `tidepool:lagoon`. Each package carries its own texture and library. Use the same packages on the server and every Innesto client.

## Prepare the target profiles once

Start with the [private client and server profiles](native-initialization.md#start-a-private-target) for the verified game installations. To obtain the stock catalogue size, start a trusted **unmodified local dedicated server** with its dashboard bound to loopback, e.g. with `--web --web-host 127.0.0.1 --webport 24711`. Use a separate vanilla data directory. From the Innesto checkout run this for each local target, substituting its absolute executable path:

```sh
tools/innesto-run --terrain-reference "$game_executable" --dashboard-port 24711
```

Add the two printed fields, `terrainPackSha256` and `terrainBaseCount`, to that target's existing private JSON profile. The installed copies must come from the same supported game build with matching stock packs. The two fields let the adapter refuse a changed stock pack and detect a different slot layout on a peer. Keep these reference values private. Stop the reference server before starting the modded instance on the same ports.

## Start a world and join

Use a **new, empty data directory** the first time. Set the shell variables to absolute paths before changing to your normal writable instance directory. On the host, for a local test:

```sh
"$innesto_root/tools/innesto-run" --profile "$server_profile" \
  --loader "$innesto_root/build/native/innesto-bootstrap.so" \
  --mods-dir "$innesto_root/build/terrain-mods" -- \
  --data-dir "$world_dir" --port 24710 --web --web-host 127.0.0.1 --webport 24711
```

Start a client with a legitimate local game directory and its normal licensed session:

```sh
"$innesto_root/tools/innesto-run" --profile "$client_profile" \
  --loader "$innesto_root/build/native/innesto-bootstrap.so" \
  --mods-dir "$innesto_root/build/terrain-mods" --terrain-peer 127.0.0.1:24710 -- \
  --game-dir "$client_game_dir"
```

Choose **Multiplayer → Direct connect** in the visible window and enter the same address, `127.0.0.1:24710`. Openworld’s own `--play HOST:PORT` starts a hidden direct client for automated sessions. Innesto also checks the peer supplied by that flag.

Before starting the client, Innesto reads the chosen server's dashboard catalogue and compares material names, absolute slots and served textures. The default dashboard TCP port is the game port plus one. Set `terrainDashboardPort` in the client profile for a different dashboard port. The client must be able to read that dashboard. These examples use loopback. The preflight applies to the selected address. Opening the menu does not restrict the game’s other server choices. It is a compatibility check at launch, so restart Innesto to change servers. The game retains its own authentication and admission rules.

## Reopen and back up a world

Innesto sorts namespaced IDs, stages a private runtime under `$XDG_CACHE_HOME/innesto/terrain` (default `~/.cache/innesto/terrain`) and runs an identical copy of the verified executable with the generated assets. It removes this copy on normal exit. The original installation and package files stay in place.

The first launch writes `innesto-terrain-v1.json` inside the dedicated world's data directory. **Back up the entire directory, including this file.** Repeat launches check the exact content set, its textures and build before the game opens the world. Reordering package directories is safe. To resume after a mismatch, restore the recorded build and original package content. A new material set needs a new world. A populated world without its registry cannot be adopted by this version.

Always reopen a managed world through Innesto. The stock executable and other launchers do not enforce Innesto's registry. The server and its clients must use matching terrain-enabled profiles. Independently launched clients are outside the launcher's preflight.
