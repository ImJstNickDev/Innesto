# Before a player breaks a block

This draft implements a synchronous veto for a simulation host that can ask
Innesto before it commits a player's block break. It targets Openworld
a1.2.10 on Linux x86-64. The interface works with the original test host in
this branch. Registration on the distributed server currently returns
`INNESTO_BREAK_UNAVAILABLE`. In-game verification is tracked in
[issue #3](https://github.com/ImJstNickDev/Innesto/issues/3).

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
| `INNESTO_BREAK_UNAVAILABLE` | The running host has no adapter for this event. |
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

## Connect and verify a simulation host

The source-level adapter in `src/block_break_host.h` receives the dispatcher
during startup, before `main`. Its setter must save the callback in storage
usable at that point. On the simulation thread, the host validates the
player's request and current block, then calls the dispatcher with the block
coordinates. A pass lets the normal break proceed once. On veto the host must
leave the block in place, suppress the drop and successful-break notification,
and send the authoritative block state if the client predicted removal. The
fixture exercises that sequence with an in-memory client view.

Acceptance on Openworld requires a connected player and a verified adapter
at that decision. Place two equivalent blocks that normally drop one item,
one at `x == 0` and one elsewhere. With both example mods active, break each
once. Check the server's block and drop state and the player's view and
success feedback on both attempts. Recheck the vetoed position after
reconnecting. Listener logs identify the attempts; the world and client
observations establish what actually happened.
