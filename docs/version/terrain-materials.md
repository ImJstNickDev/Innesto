# Terrain materials

A shared native package can register terrain materials on a dedicated server and the clients that join it. Each material has a stable ID, an original texture and a family that the game uses for rendering and gameplay. The two examples can be collected and placed in Survival. [Try the player walkthrough](terrain-survival.md).

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

## Can registered materials generate naturally?

Innesto's a1.2.10 content contracts (versions 1–3) cover material identity, appearance and gameplay family. They expose no rule for abundance, deposit size, altitude, biome or planet. Selecting the plant family gives a placed material its vegetation behavior. It does not add that material to a biome's plant selection.

Openworld uses a seed and terrain layout to generate new columns. Its inspector describes the surface materials and vegetation of each biome and reports the positions, sizes and materials of native deposits. The game also documents where players can find its native ores. [Openworld resource guide](https://www.play-openworld.com/en-gb/guides/exploration/how-to-find-resources-oil-ores/)

In fresh dedicated worlds with the same seed, Copperfield and Reedbed added two catalogue entries. The biome descriptions and sampled deposit and tree instances matched the stock server on Earth and the Moon. The sampled voxel material IDs also matched, including native ores. Changing the seed changed the sampled terrain. In a separate Survival session with Copperfield, Reedbed and Aster installed, the dedicated server served fresh terrain to a connected client. Its live map showed the same surfaces and mesh as the stock world across 25 columns, including after restart.

Innesto needs a verified dedicated-server interface that binds a world's persistent material ID to a generation rule or selects that material while creating a new column, before the column is saved. The inspector exposes its rules for reading. The celestial map controls planet properties. The authored estate tested in solo was a one-time build tied to one seed and layout. None provided a verified rule input for natural multiplayer generation. Natural harvesting and the behavior of existing worlds when adding generation rules remain unverified. [Track world generation in issue #47](https://github.com/ImJstNickDev/Innesto/issues/47).

## Choose terrain properties in version 2

Set `content.version` to `2` to select a material family. You can also set the tile size reported in the server catalogue. These fields apply to each material. A package can contain several families.

```json
"content": {
  "version": 2,
  "assets": "assets",
  "terrain": [
    { "id": "reedbed:rush", "texture": "rush.png", "family": "plant", "tileMeters": 0.5 }
  ]
}
```

| Family | Dedicated server classification |
| --- | --- |
| `rock` | Solid, opaque terrain. The default. |
| `plant` | Non-solid vegetation with cutout rendering. |
| `crop` | Non-solid terrain with cutout rendering. The server does not mark it as vegetation. |
| `foliage` | Solid terrain with cutout rendering. |
| `glass` | Solid terrain with blended rendering. |
| `liquid` | Non-solid terrain classified as liquid. |

The server applies these properties to placed voxels. It counted an elevated rock pad as the terrain surface, looked through an equally sized plant pad to the stone below and reported liquid depth for a liquid pad. Suspended rock stayed in place. Plant voxels placed above open air disappeared and could be placed again in the same cells. The contract provides the game's family behavior. Growth rules, flow, drop tables and new recipes have no registration fields in this version.

`tileMeters` accepts `0.25`, `0.5`, `1`, `1.5`, `2` or `2.5`. The default is `1`. The dedicated server reports this value in its catalogue. Its 3D dashboard map repeats the texture four times across a metre at `0.25` and once at `1`. The connected game client showed the same checker spacing at `0.5` and `2` in a side-by-side test. Version 1 materials keep their original rock definition and value of `1`. Writing those same defaults in version 2 preserves the existing material binding.

### Name a material in the player's language

In version 2 a material can supply a `displayNames` object, for example `{"it": "Giunco", "fr": "Jonc", "en-GB": "Rush"}`. The connected client uses the selected language on the **I** knowledge card. The Italian name also appeared on the target label and in the pickup notification during a Survival session. Regional selections follow the game's own fallback order. Default English (`en`) uses the generated name. British English (`en-GB`) accepts a supplied translation. The operator key and saved material ID stay the same in every language.

Use the exact locale code from this list:

```text
ar bn ca cs da de de-CH el en-GB es es-419 fa fi fil fr fr-CA he hi hu id it ja ko
mr ms nb nl pl pt-BR pt-PT ro ru sv sw ta te th tr uk ur vi wa zh-Hans zh-Hant
```

A name is 1–64 characters after Unicode NFC normalization, on a single line without leading or trailing whitespace or control characters. Innesto stages translations into the client's private runtime. Only the mod's own names belong in the package.

### Animate a texture

The optional `frames` field lists up to 15 **additional** images in playback order. The `texture` field supplies the base image. For example, `"texture": "ember.png", "frames": ["ember-bright.png", "ember-dim.png"]` uses three mod-owned 32 × 32 RGBA PNGs under the asset directory. Omit `frames` or use an empty array for a static tile. Playback uses the game's timing.

## Install both examples

From a Linux x86-64 checkout of `game/a1.2.10`, build each mod independently. Install into a fresh example directory on each peer. CMake keeps other packages already installed under the same prefix.

```sh
cmake -S . -B build/native
cmake --build build/native
for mod in copperfield reedbed; do
  cmake -S "examples/$mod" -B "build/$mod" -DINNESTO_INCLUDE_DIR="$PWD/include"
  cmake --build "build/$mod"
  cmake --install "build/$mod" --prefix "$PWD/build/terrain-survival-mods"
done
```

This installs `copperfield:ochre` (rock, version 1) and `reedbed:rush` (plant, version 2). The original `tidepool` package is also available for worlds created with the two version 1 examples. Each package carries its own texture and library. Use the same packages on the server and every Innesto client.

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
  --mods-dir "$innesto_root/build/terrain-survival-mods" -- \
  --data-dir "$world_dir" --port 24710 --web --web-host 127.0.0.1 --webport 24711
```

Start a client with a legitimate local game directory and its normal licensed session:

```sh
"$innesto_root/tools/innesto-run" --profile "$client_profile" \
  --loader "$innesto_root/build/native/innesto-bootstrap.so" \
  --mods-dir "$innesto_root/build/terrain-survival-mods" --terrain-peer 127.0.0.1:24710 -- \
  --game-dir "$client_game_dir"
```

Choose **Multiplayer → Direct connect** in the visible window and enter the same address, `127.0.0.1:24710`. Openworld’s own `--play HOST:PORT` starts a hidden direct client for automated sessions. Innesto also checks the peer supplied by that flag.

Before starting the client, Innesto reads the chosen server's dashboard catalogue and compares material names, absolute slots and served texture receipts. For each material, the receipt covers the base texture, family, catalogue tile size, translations and ordered frame contents. A transferred material also commits to the installed provider. Both peers need matching packages. The launcher stages client materials in the dedicated world’s slot order and checks the slots and receipts again before starting the game. The default dashboard TCP port is the game port plus one. Set `terrainDashboardPort` in the client profile for a different dashboard port. The client must be able to read that dashboard. These examples use loopback. The preflight applies to the selected address. Opening the menu does not restrict the game’s other server choices. Restart Innesto to check a different server.

## Reopen and back up a world

Innesto stages a private runtime under `$XDG_CACHE_HOME/innesto/terrain` (default `~/.cache/innesto/terrain`) and removes it on normal exit. A new dedicated world assigns its first slots in namespaced ID order. Its registry records each material ID, absolute slot, gameplay definition and visual revision. Each later launch restores that order, including when package directories are renamed.

**Back up the entire stopped world directory**, including `innesto-terrain-v1.json`. The filename is shared by all registry schemas so older Innesto launchers can recognize a protected world. The launcher opens schema 1 worlds created by earlier game-branch builds with their original packages and registry bytes. Worlds from the initial family-and-scale development build require one offline enrollment with the original assets before reopening. Populated worlds without their registry require a complete matching backup. Use Innesto for every launch of a managed world.

## Add a content package to an existing world

Stop the dedicated server before copying, moving or replacing its data directory. Keep a complete backup of the world. Install the additional shared package alongside the original packages. For example, to add Aster to the Copperfield and Reedbed installation above:

```sh
cmake -S "$innesto_root/examples/aster" -B "$innesto_root/build/aster" \
  -DINNESTO_INCLUDE_DIR="$innesto_root/include"
cmake --build "$innesto_root/build/aster"
cmake --install "$innesto_root/build/aster" --prefix "$innesto_root/build/terrain-survival-mods"

"$innesto_root/tools/innesto-run" --migrate-terrain --profile "$server_profile" \
  --loader "$innesto_root/build/native/innesto-bootstrap.so" \
  --mods-dir "$innesto_root/build/terrain-survival-mods" -- --data-dir "$world_dir"
```

The migration stages the proposed pack and validates it while holding the world lock. It runs offline and updates only registry files. Existing materials keep their absolute slots. Innesto rejects a catalogue that exceeds the native 16-bit slot range. Newly installed IDs receive consecutive slots after the last binding, sorted only within that batch. In this example, `aster:chalk` follows `copperfield:ochre` and `reedbed:rush`. Install the matching package on each client, then use the normal server and client commands above. The client obtains the world's order from the dedicated dashboard.

The same command enrolls a schema 1 world into schema 2. Supply the **original definitions and assets for every saved material** on that first migration. You may add new materials in the same step. The old registry contains a single receipt per material, so it takes the original package to separate its permanent binding from its appearance. New worlds use schema 2 immediately.

## Update a texture or recover a migration

An enrolled world accepts a replacement base PNG for a **static rock whose pixels are all opaque**, with the same ID, family, tile size and names. For example, change the RGB artwork for `copperfield:ochre` and install the updated package on both peers. Stop the server and run the migration command again. The slot and inventory identity stay fixed, the material’s revision advances and a client with the previous artwork fails preflight. Normal startup requires the recorded revision. Changing material family, transparency, frame sequence, names or tile size, editing another family's texture, and removing or renaming a saved ID are refused. To retire a package while retaining its material, follow [Replace a missing terrain package](missing-terrain.md).

A successful migration retains the exact previous registry as `innesto-terrain-v1.json.backup-<sha256>` and atomically replaces the active registry. Repeating the same migration is safe. After an interrupted migration, keep the candidate packages installed and preview again. If the original command used a full backup, follow the [backup retry procedure](missing-terrain.md#reinstall-or-recover). If it reports an incompatible or missing definition, restore the required package before retrying. To return to a world that predates a successful migration, restore its **complete matching world backup and packages together**. Restoring an old registry alone could reinterpret terrain or inventory written in a newer slot.
