# Writing a mod API

Start a proposed API with the smallest example a mod author would write.
Review that example alongside the implementation and exercise it as a
separately built mod. Keep the tested example in the same version branch as
its reference page.

## Document the contract

For each entrypoint or callback, document the owning module, the supported game
version and platform, and the first Innesto version providing it. Describe when
it runs, on which side and thread, which arguments can be modified, and how
long callers can retain any handles they receive.

For an event, specify what happens with zero, one and multiple listeners.
State the order guarantees, the effect of a return value and what later
listeners observe. Distinguish a proposed action from its completed outcome
when an earlier listener can veto it.

For registered content, document who assigns its identifier, what happens on
a duplicate, and how a mod author can verify the result after saving, reloading
or connecting another player, wherever those operations apply.

## Verify the example

Exercise the default behavior and the changed behavior. For an API intended
for several mods, include a second mod in at least one scenario. Document the
observable result and the command or in-game action that produces it. Keep
private game details in the maintainer workspace.

When changing a published contract, describe the effect on existing mods for
that game version. If authors must update their code, include a migration
example in the same change.

These conventions draw on the
[Fabric API development guidelines](https://github.com/FabricMC/fabric-api/blob/495da79f62942fa2630b576ce2075536d37b8223/CONTRIBUTING.md).
