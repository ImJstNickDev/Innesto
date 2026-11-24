# Replace a missing terrain package

If a saved material's provider is missing, Innesto stops before the dedicated server opens the world. The error lists the persistent IDs, slots and required providers. Reinstalling the recorded packages on both peers is enough to reopen the world. Keeping copies of those packages is an operator choice. Innesto does not archive mod libraries or artwork when a package is uninstalled.

A different shared package can take responsibility for an existing material. The world keeps its original ID, numeric slot and visual revision. The new provider supplies the complete definition and artwork on both peers. The transfer must reproduce the saved family, tile size, names, frames and texture bytes. A package making an eligible RGB update should do that in a separate migration.

## Declare a replacement

The independently buildable Kiln example ships the same original ochre texture as Copperfield. Its content contract is version 3. A new world created with Kiln assigns a slot to `kiln:ochre`. In an existing Copperfield world, the operator can explicitly bind Kiln to `copperfield:ochre`.

```json
"content": {
  "version": 3,
  "assets": "assets",
  "terrain": [
    {
      "id": "kiln:ochre",
      "texture": "ochre.png",
      "aliases": ["copperfield:ochre"]
    }
  ]
}
```

An alias names a **persistent ID** directly. Each saved slot needs its own installed material. Aliases cannot shadow an installed ID, form chains or assign one provider to two slots. Installing both Copperfield and this Kiln example together creates a conflict. Version 1 and 2 packages keep their existing contracts.

## Preview and apply offline

Stop the dedicated server, including any server started outside Innesto. Use the same pinned server profile as for normal play. Prepare a separate package directory (`next_mods`) containing Kiln and every other required package. Keep the old package set available for rollback. To build Kiln into that directory from the Innesto checkout:

```sh
cmake -S examples/kiln -B build/kiln -DINNESTO_INCLUDE_DIR="$PWD/include"
cmake --build build/kiln
cmake --install build/kiln --prefix "$next_mods"
```

Preview against the stopped world's data directory. Neither the preview nor the migration starts the game or initializes native mods.

```sh
tools/innesto-run --profile "$server_profile" --loader build/native/innesto-bootstrap.so \
  --mods-dir "$next_mods" --preview-terrain \
  --remap-terrain copperfield:ochre=kiln:ochre -- --data-dir "$world_dir"
```

Check the displayed slots, providers and revisions. Multiple transfers can be requested by repeating `--remap-terrain`. To apply, choose a new directory beneath an existing backup parent on a filesystem with enough space for the whole world. Keep it separate from the world, installed game, runtime cache and packages.

```sh
tools/innesto-run --profile "$server_profile" --loader build/native/innesto-bootstrap.so \
  --mods-dir "$next_mods" --migrate-terrain --backup-world "$backup_parent/before-kiln" \
  --remap-terrain copperfield:ochre=kiln:ochre -- --data-dir "$world_dir"
```

Innesto locks the world directory, checks the complete proposed set, copies every regular file and directory under the data root and verifies the copy against the source. A symlink, special file, copy error, changed source or differing existing backup stops the operation. Once the full backup is durable, Innesto atomically publishes the registry. Terrain, player saves and inventories keep their original bytes during the transfer. No other directory is included in the backup. Keep external configuration and packages separately.

Restart with the normal Innesto launch command and the replacement package set. Clients need the same provider and assets. The peer check binds the served material to its provider, so a client still running Copperfield will fail preflight even though the pictures match. A transferred world uses registry schema 3 and requires a launcher that understands it.

## Reinstall or recover

- **Return to the original provider while keeping newer gameplay.** Stop the server. Prepare the original package set on both peers. Repeat the preview and apply commands with `--remap-terrain copperfield:ochre=copperfield:ochre` and a fresh backup destination. The left side always names the permanent world ID. An exact original definition needs no alias.
- **Recover an earlier world.** With the server stopped, copy the complete backup to a separate data directory, preserving its contents and metadata. Open that directory with its matching packages and pinned profile. This restores player and terrain state at the time of the backup. Retain the current world separately.
- **Resume an interrupted transfer.** Preview with the same candidate packages. If it reports the requested provider is already current, the registry was published. Otherwise retry the same transfer. Innesto reuses an existing backup only when its entire contents and metadata match the stopped world. If the directory has since changed, including transaction files or a changed modification time, keep the first backup and use a fresh destination for the retry. Restoring an older registry file by itself can change the meaning of saved slots.

In the a1.2.10 multiplayer test, the same player rejoined with Kiln, after a full restart, after reinstalling Copperfield and from a separate restore of the pre-transfer backup. The ochre wall still rendered, the hotbar held the same 19 pieces, and inventory and edited terrain survived each reopening. Clients with the previous provider, a missing provider or a changed texture failed preflight.

## Why a slot stays occupied

On a disposable dedicated server, omitting a middle catalogue entry moved the next material into its numeric slot. A populated multiplayer inventory held a stack at the original number. Keeping the declaration with a missing or empty texture preserved the number but left no usable texture. Substituting an ordinary rock for a plant changed solidity and rendering. Innesto reserves the slot by retaining its verified definition through an installed provider. There is no general purge or automatic placeholder policy. A destructive removal would require complete coverage of every place the game can persist that identity.

## Can I delete the material from my world?

On a1.2.10, removing Copperfield from the package directory makes Innesto refuse to open a world that still binds its material. To inspect a stopped world, point the existing preview at the proposed package directory, including the mods you intend to keep.

```sh
tools/innesto-run --profile "$server_profile" --loader build/native/innesto-bootstrap.so \
  --mods-dir "$next_mods" --preview-terrain -- --data-dir "$world_dir"
```

For missing providers the command exits with an error. It lists the missing IDs and slots, the number of surviving slots that would move if just those rows were dropped, and the first such move. For example, in a world created with Copperfield and Reedbed and later extended with Aster, removing Copperfield would move both remaining materials. Even a missing material in the last slot can still occur in terrain and inventories. Counts of affected voxels and stacks are unknown. Applying this package set with `--migrate-terrain` also stops before writing a backup or changing the world.

### What the game tools could verify

- **Terrain.** A native operator edit at a known location persisted real AIR across a restart. At a different location, one metre-wide edit erased voxels of two different materials. A selective editor must find and change only matching voxels throughout every saved region and planet, including unloaded ones.
- **Stored items.** The saved player held 19 ochre in one stack and had a separate discovery entry for the same material. Containers also persist their contents on the server. A complete purge needs an item-aware traversal and writer for occupied containers and other item stores, including cargo and machine filters. The dashboard counted loose items in a controlled test, but did not identify each stack. Whether all drop types can reload is unresolved. [Openworld chest guide](https://www.play-openworld.com/en-gb/wiki/getting-started/interface-inventory-chests/)
- **Verification.** The native world verifier accepted a populated world and an identical backup both with the original catalogue and with Copperfield absent. A separately started server showed that Reedbed then occupied Copperfield's former slot. In another control, changing only whitespace in a player save made the verifier report a difference. It compares the bytes of that file and cannot certify item-level edits.

Until these references can be counted and rewritten, keep the recorded packages to reopen the world or use the explicit equivalent-provider transfer above. [Track destructive removal in issue #45](https://github.com/ImJstNickDev/Innesto/issues/45).
