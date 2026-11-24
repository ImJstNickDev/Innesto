# Before a player breaks a block

An Innesto version adapter connects a block-break decision inside the simulation
to mod listeners. The simulation checks a proposed edit before removing the
block, dropping an item or confirming success to the player.

The draft targets Openworld a1.2.10 on Linux x86-64. It works in the adapted
native test executable. The distributed server still returns
`INNESTO_BREAK_UNAVAILABLE` because its decision site has yet to be connected.
[Issue #3](https://github.com/ImJstNickDev/Innesto/issues/3) tracks in-game acceptance.

## Write a listener

Include the header from this branch and register the listener during
`innesto_mod_init_v1`. This example requires the event to operate and stops
startup if registration fails.

```c
#include <innesto/block_break.h>
#include <innesto/mod.h>

static int keep_block(const struct innesto_block_break_v1 *attempt)
{
    return attempt->x == 0 ? INNESTO_BREAK_VETO : INNESTO_BREAK_PASS;
}

int innesto_mod_init_v1(void)
{
    return innesto_register_before_block_break_v1(keep_block)
           != INNESTO_BREAK_REGISTERED;
}
```

The arguments are signed, 32-bit world block coordinates. The simulation
thread owns the decision and calls listeners synchronously. The read-only
snapshot is valid only until the callback returns. Copy individual coordinates
to retain them. A listener can veto the proposed edit by its return value.

Listeners run in registration order, which follows mod initialization order
across packages. With zero listeners the decision is `PASS`. Each `PASS`
continues to the next listener. The first `VETO` ends dispatch. Any unexpected
nonzero result also vetoes the edit. An early listener sees an attempt that a
later listener may still deny.

| Registration result | Meaning |
| --- | --- |
| `INNESTO_BREAK_REGISTERED` | Innesto retains this callback for the process lifetime. |
| `INNESTO_BREAK_UNAVAILABLE` | A version adapter did not attach this decision site during startup. |
| `INNESTO_BREAK_INVALID` | The listener pointer is null. |
| `INNESTO_BREAK_CLOSED` | Registration was attempted outside initialization on the loader thread, or from another thread. |
| `INNESTO_BREAK_NO_MEMORY` | The loader could not retain this listener. |

Registration appends one listener per successful call. A mod that uses the
event optionally can continue without it on `UNAVAILABLE`. Build these mods
with the draft header and loader from the same checkout. Earlier loaders lack
the registration function.

## Run the example

From the repository root, run the tests on Linux x86-64 with the
[native build prerequisites](native-initialization.md#build-the-loader-and-example).

```sh
cmake -S . -B build/native
cmake --build build/native
ctest --test-dir build/native -R block-break --output-on-failure
```

The test builds and installs `examples/break-audit` and `examples/break-guard`
as independent packages. The guard declares the audit mod as a dependency.
Audit records each attempt. Guard vetoes attempts where `x == 0`.

| Attempt in the fixture | Simulation | Modeled client |
| --- | --- | --- |
| Allowed, followed by a retry on the empty position | Block removed, one drop | One success, block absent |
| Vetoed after predicting removal | Block intact, zero drops | Block restored, zero successes |

## How the decision reaches a mod

The loader supplies `innesto_adapter_attach_before_block_break_v1` to the
version adapter. The adapter owns the call at the decision site and attaches
it at startup. Innesto closes attachment before opening any mod libraries.
An attached site can dispatch to listeners after all mod initializers succeed.
The game's executable can keep its gameplay functions private.

The tests build two executables from the same simulation object files. One
runs its original block rule. The other links an adapter at that internal
rule. The original rule runs first, so an attempt to break an already empty
position never reaches the listeners. For a valid attempt, the adapter asks
Innesto for a decision before the simulation edits the block. A pass continues
the normal action. On veto the fixture preserves the block and corrects the
predicted state in its modeled client.

## Verify the game integration

A live control on the dedicated server confirmed one ordinary break, one
drop and one matching item collected. That run used startup-only mods. The
adapter used in the tests is specific to the test simulation.

Acceptance on Openworld requires a connected player and a verified adapter
at that decision. Place two equivalent blocks that normally drop one item,
one at `x == 0` and one elsewhere. With both example mods active, break each
once. Check the server's block and drop state and the player's view and
success feedback on both attempts. Recheck the vetoed position after
reconnecting. Listener logs identify the attempts; the world and client
observations establish what actually happened.
