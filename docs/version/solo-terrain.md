# Play a Solo Survival world with terrain mods

Start Openworld through Innesto and select **Solo**. The client starts its bundled local host when you enter the world. Both processes read the same staged material pack. Native client and shared mod entrypoints run on the physical client. The local host owns the simulation and reads the terrain declarations.

## Prepare the client

Use your activated Linux x86-64 a1.2.10 installation, a [private client profile](native-initialization.md#start-a-private-target), and [independently installed terrain packages](terrain-materials.md#install-both-examples). Managed Solo also requires Bubblewrap with user, PID and network namespace support and the `--lock-file` and `--sync-fd` options. The session uses loopback. License activation and account management stay with the official launcher.

Capture one stock session from the executable named by the client profile. Set `game_client` to its absolute path, enter a disposable vanilla Solo world with the stock pack, wait for terrain to render, then **Save & Leave** and quit. The console capture contains private session data. Keep it local.

```sh
umask 077
"$game_client" > "$stock_solo_log" 2>&1
tools/innesto-run --solo-reference "$client_profile" --stock-solo-log "$stock_solo_log"
```

Add the three printed fields to your private client profile. Innesto checks the installed helper and stock pack against these pins before each launch. Use a new capture if you move the installation. An existing multiplayer terrain profile with matching stock pins needs just the new `soloHostSha256` field.

## Create and reopen a world

Choose a new directory outside the ordinary client saves, packages and game installation. Its final path component is the display name in the Solo menu. Here the world is called Birch.

```sh
world="$HOME/Innesto-worlds/Birch"
tools/innesto-run --profile "$client_profile" \
  --loader build/native/innesto-bootstrap.so --mods-dir build/terrain-survival-mods \
  --solo-world "$world"
```

Select **Solo**, choose **Birch** and press **Play**. First launch prepares a Survival world with a new seed. The chooser exposes just this world. **Esc → Save & Leave** finishes the native save. Quit the client, then use the same command to reopen it. For a second world, choose another directory. Each world keeps its own registry, terrain and player inventories. Keep the entire directory together when moving or backing it up.

To try the two example materials in a fresh world, switch to Creative to place sample terrain on suitable ground, then switch back to Survival to harvest it. Rush needs support. Select the collected stacks in the hotbar to hold and place them. The [Survival walkthrough](terrain-survival.md) gives the ochre chisel recipe. The example packages register materials; natural deposit generation is tracked separately. [Game mode controls](https://www.play-openworld.com/en-gb/wiki/mechanics/game-modes/)

## Add a package to a played world

Exit the client completely. Install the additional package in the same mods directory. Preview the proposed slot assignments, then apply the change. The backup destination must be a separate path outside ordinary client saves.

```sh
tools/innesto-run --profile "$client_profile" \
  --loader build/native/innesto-bootstrap.so --mods-dir build/terrain-survival-mods \
  --solo-world "$world" --preview-terrain

tools/innesto-run --profile "$client_profile" \
  --loader build/native/innesto-bootstrap.so --mods-dir build/terrain-survival-mods \
  --solo-world "$world" --migrate-terrain --backup-world "$backup_dir"
```

Launch normally after migration. Additions append after the world's existing materials regardless of package discovery order. If a provider is missing, restore its recorded package. If the launcher reports a definition mismatch, restore the compatible definition or preview a [supported migration](missing-terrain.md). A populated ordinary save cannot be enrolled by pointing `--solo-world` at it. Restore a managed save together with its complete registry and matching packages.
