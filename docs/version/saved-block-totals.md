# Read a player's saved block totals

An API 2 mod on a dedicated a1.2.10 Linux x86-64 server can query the most recently saved number of blocks a player has broken and placed. The optional adapter reads the operator-selected world, including records of offline players. It first ships on the a1.2.10 development branch.

```c
#include <innesto/runtime.h>
#include <innesto/saved_blocks.h>

int has_placed_blocks(const struct innesto_mod_context *context, const char *player_uuid)
{
    const struct innesto_saved_blocks_v1 *stats =
        innesto_query_capability_v1(context, INNESTO_CAP_SAVED_BLOCKS, 1);
    if (stats) {
        struct innesto_saved_block_totals_v1 totals;
        if (stats->read(player_uuid, &totals) == INNESTO_SAVED_BLOCKS_OK) {
            return totals.placed > 0;
        }
    }
    return 0;
}
```

The table remains valid for the process lifetime. Call `read` on a thread where synchronous file I/O is appropriate. Concurrent calls use separate file descriptors. Supply a lowercase, hyphenated UUID and caller-owned output storage. Each call opens the current record in the directory bound at startup, so a subsequent read sees an atomically replaced record. The game controls when progress is saved. Polling can miss intermediate totals, and restoring a save can lower them.

| Result | Meaning |
| --- | --- |
| `INNESTO_SAVED_BLOCKS_OK` | Both totals were read together. Zero is a valid count. |
| `INNESTO_SAVED_BLOCKS_INVALID_ARGUMENT` | Invalid UUID or output pointer. |
| `INNESTO_SAVED_BLOCKS_NOT_FOUND` | The selected directory contains no record for this UUID. |
| `INNESTO_SAVED_BLOCKS_UNREADABLE` | The record could not be read as a stable regular file. A later read may succeed. |
| `INNESTO_SAVED_BLOCKS_INVALID_RECORD` | Invalid JSON, unexpected revision or player, or invalid counters. |

On failure, the output retains its previous value. A snapshot has no per-action coordinates, ordering or cancellation result. A mod that needs a decision before removal must query the separate [before-block-break capability](before-block-break.md).

## Bind a world

Build the loader with Jansson 2.11 or newer and its development headers; the default build omits this adapter.

```sh
cmake -S . -B build/reader -DINNESTO_SAVED_BLOCKS=ON
cmake --build build/reader --target innesto-loader
```

Create a private JSON binding. Use the independent reference fingerprint for the distributed dedicated server, an absolute path to the selected world's player-statistics directory, and the record revision and four distinct top-level property names validated for that save format. The record filename is the lowercase player UUID followed by `.json`. Below, the property names and revision illustrate an original example schema. For a local binding, match the record UUID to its filename and verify both counters against the player's operator statistics at two checkpoints where the totals differ. Keep the resulting binding private. [Openworld player statistics](https://www.play-openworld.com/doc/moderation/)

```json
{
  "serverSha256": "<verified lowercase SHA-256>",
  "directory": "/absolute/path/to/player-statistics",
  "revision": 7,
  "fields": {
    "revision": "schema",
    "player": "owner",
    "broken": "removed",
    "placed": "added"
  }
}
```

The indicated revision and counters must be JSON integers. Counters range from zero to the maximum signed 64-bit integer. The player identifier in the record must exactly match the requested UUID. The adapter reads a regular binding file and skips symbolic links for individual records. Set `INNESTO_SAVED_BLOCKS_BINDING` to the absolute path of the binding file when launching. A missing binding, client process, mismatched executable identity or inaccessible source makes the capability unavailable. Use a directory belonging to the world being served; the operator selects it explicitly.

## Run the example

From the checkout, build the package independently. Set `profile` to your private server launch profile and `packages` to a dedicated mods directory.

```sh
cmake -S examples/saved-blocks -B build/saved-example -DINNESTO_INCLUDE_DIR="$PWD/include"
cmake --build build/saved-example
cmake --install build/saved-example --prefix "$packages"
```

Use the server's usual working directory and game arguments. Set `innesto_root` to the checkout, `binding` to the private binding file, and `player_uuid` to a player with saved progress in the selected world.

```sh
INNESTO_SAVED_BLOCKS_BINDING="$binding" INNESTO_EXAMPLE_PLAYER_UUID="$player_uuid" \
  "$innesto_root/tools/innesto-run" --profile "$profile" \
  --loader "$innesto_root/build/reader/innesto-bootstrap.so" --mods-dir "$packages" -- "$@"
```

The example reads once during initialization and prints `saved-blocks: broken=N placed=M`. Compare both totals with the selected player's operator statistics. This comparison passed for an offline player at two real gameplay checkpoints on the distributed dedicated server. [Acceptance record](https://github.com/ImJstNickDev/Innesto/issues/31)
