# Native lifecycle and gameplay evidence for a1.2.10

On Linux x86-64, the dedicated server entered its simulation loop with the native material registry populated. The same storage was still present when shutdown was saving the world. An independently built mod can run earlier, during loader startup. This campaign found no verified host interface that delivers that mod into the intervening execution context. Issue #55 remains open. [Material Registry acceptance](https://github.com/ImJstNickDev/Innesto/issues/55)

## Catalogue and review scope

| Measure | Revision 5 | Revision 6 |
| --- | ---: | ---: |
| Unique native functions | 62 | 93 |
| Distinct function semantic identifiers | 43 | 74 |
| Independently verified function semantics | 9 | 18 |
| Verified machine contracts | 3 | 5 |
| Active game-native bindings | 0 | 0 |

The unit of identity is an entry in an exact executable image. The dedicated server and bundled Solo host share one image. The physical client has another. A second execution role can independently support a behavior without adding a function. Counts exclude library helpers, unattributed neighbors, source-file names and repeat visits. A machine contract describes checked operands and results under stated conditions. Enabling a mod capability also requires delivery, lifetime and an individually reviewed resolver. [Catalogue methodology](research-catalog.md)

A first-pass survey of eleven resource, interface and storage families found 157 candidate extents in the client and 43 in the server, with 470 direct references. Eight extents were already catalogued. Nineteen new functions passed a second check of how distinct references reached an actual consumer. The rest stayed in the private discovery inventory. A separate five-by-five BSim comparison ranked each expected registry pair first in both directions. Exact instruction and mnemonic Version Tracking agreed on four pairs. None matched by exact bytes. The name resolver ranked first at 0.761 and lacked an exact match. Its client and dedicated variants already have different evidence about a writable result operand.

### Newly mapped functions by subsystem

| Subsystem | New functions and purposes | Verification |
| --- | --- | --- |
| Dedicated lifecycle and simulation | Restore the world clock during startup, enter the loop that schedules saves, flush the clock on shutdown, and supply an autosave reason from another caller. | The first three operations have direct phase observations. The additional caller has static evidence. A large extent can contain other operations besides the one named here. |
| Dedicated material registry | One routine registered to release registry storage. | Its cleanup purpose is verified on two standalone diagnostic configurations. Its calling contract for extensions remains unknown. |
| Dedicated persistence | Save the world clock, prepare component-save filenames, flush chest and machine stores separately, and serialize each store's records. | Clock saves and both successful store flushes have independent runtime and file evidence. The two encoders have high-confidence static and format evidence. Filename preparation has medium-confidence static evidence. |
| Dedicated factory simulation and generation | One extent contains a generator-completion diagnostic. Two other extents consume separate sets of geometry descriptor fields for column/tile and soil/cell data. | The generator context is discovered. The two field consumers are inferred. A rule-registration or material-selection decision was outside the demonstrated operations. |
| Physical client rendering | Thirteen extents prepare shader-stage resource names for different parts of the renderer, including the interface, sky, weather, entities and screen effects. A separate function reads the two interface stages into caller-supplied storage. | Stack-attributed opens verify the interface path. Five successful returns and one failed return verify a bounded machine contract for its reader. The other twelve resource-name uses are static inferences. |
| Physical client interface and assets | Compare control-event names, prepare glyph and interface atlas diagnostics, and prepare sound-effect resource paths. | Three medium-confidence static inferences. Supplying a name to a string consumer establishes neither file access nor playback. |

### Dedicated execution and registry lifetime

Four fresh-world and two restored-clock processes covered stock and two-material packs. All six entered the loop on the process leader. At all 94 observed phase points, the initialization flag was set, and the same allocation bounds within each process accounted for 435 or 437 slots. The saved-clock restoration point ran in the two restored worlds. The 74 autosave and six final-save observations agreed one for one with the game's clock records. Each final tick count also matched the stopped world's file. Two runs stopped by normal duration expiry and four by console command.

The earlier four-boot mod experiment found the registry cold at all eight initializer and startup-complete checkpoints. The new measurements bracket a useful interval on dedicated. They also reject a proposed admission test based on the publication flag alone. The flag was still set inside shutdown. The experiment establishes observations at specific points. Concurrent access, exclusive ownership and the right to retain an object across callbacks need separate evidence.

A separate shutdown study used stock and 8,627-slot registries. Four serving processes registered the same cleanup routine. None entered it on a normal console or duration stop, and all four exited successfully. Four standalone diagnostics on the same executable entered it. In the two more detailed diagnostic controls, the storage transferred for deallocation matched the live array base and capacity. A process-level cleanup registration therefore cannot supply a reliable last callback for a dedicated world.

The ordinary numeric lookup takes an in-range material ID and returns the corresponding registry-owned row. In three clean paired trials, 5,944 observed normal returns satisfied the indexed selection and stored-ID check. The largest distinct input set was 363 slots per pack. Every independently projected ID, exact name and available texture key in the complete 435- and 437-row tables agreed with the operator's catalogue. Dashboard reads ran on a secondary thread. The sampled operator-command reads ran on the leader. Fourteen further full catalogue responses returned the correct tail entries. An independent read observer saw the final native name fields during ordinary operator name lookups up to IDs 434 and 436. The watched fields had no observed reads during those dashboard requests. Direct indexed returns above slot 362 remain unverified at runtime. These observations give the numeric accessor a bounded machine contract. In-range selection and execution from an arbitrary mod are separate review decisions.

A further six dedicated processes tested the operator interface independently. Across 16 replies, Earth and Moon returned identical ordered material rows within each stock or extended configuration, despite different planet metadata. The verified name controls included a true hit at slot zero, a miss, case, a differing display key and the final slot. All four web-enabled runs produced a reply before the first periodic serving report. Both web-disabled servers reached that report. A copied catalogue remains readable after the process exits. HTTP availability and a serving log line therefore fail as mod callback or pointer-lifetime signals. [Publisher's server documentation](https://www.play-openworld.com/doc/)

### Physical client and native Solo

The physical client loaded two separately built API 2 packages. Their two initializers and two startup-complete callbacks ran before the first main menu, with logical side unknown. A player entered and left the same Solo world twice in an isolated display. The physical client kept its PID. Each visit had a different direct-child host, and each child exited normally on leave. At the interactive checkpoints the bootstrap and selected modules were mapped in the parent. Neither child had any of those modules mapped at its checkpoint.

Four further physical-client boots measured the registry in the client itself. All eight public mod checkpoints preceded publication. All eight menu and post-menu checkpoints had 435 stock or 437 extended slots. The client separately reported 259 or 261 interface resources. The two counts rose together when the pack changed but measure different populations. Two additional standalone launches of the genuine bundled helper, with no player or parent client, had 435 or 437 slots at four ready and later checkpoints. Those helper measurements establish a serving state for that launch mode. The interactive two-visit experiment above establishes actual parent/child lifetime.

Two independent menu launches under a software Vulkan renderer recorded successful opens for both UI shader stages. Call stacks attributed those opens to the same client reader. A stock, missing-fragment, stock sequence then isolated its return behavior. All five successful output byte ranges matched the corresponding installed file exactly. The omitted stage returned an empty output and failure, and the client exited with status 1. Both intact controls reached the menu and exited successfully. The low byte carries the observed success status. Higher bits varied on success. The destination belonged to the caller and started empty in all six observations. Drawing, GPU submission and replacement of resources by a mod were outside these checks.

### Crafting, inventories and world simulation

Nine disposable boots of one furnished estate tested which stored state drives machine activity. Six used the dedicated server and three used the bundled host with normal local trust setup and no player. The latter runs are separate from the two interactively entered Solo sessions. All nine exited normally.

| Copied-world condition | Chest records loaded | Machine records loaded | Locations completing generator operations |
| --- | ---: | ---: | ---: |
| All stores present | 33 | 9 | 5 |
| Chest stores omitted | 0 | 9 | 5 |
| Machine stores omitted | 33 | 0 | 0 |
| Factory network snapshot omitted, dedicated only | 33 | 9 | 5 |

All 33 containers held at least one stack. In total, 126 of 1,188 positions were occupied. Two stock item identities also agreed with independently labeled player-inventory data. Machine records held variable numbers of item slots. Another section had a different representation and remains uninterpreted. Instance location allowed comparison when the save order changed.

Omitting machine storage stopped the observed operations while the dedicated dashboard continued to show nine machine devices and 382 network nodes. Omitting the network snapshot rebuilt the topology but reset accumulated state. A dashboard device count cannot establish which machine buffers will survive removal. An occupied stock estate supplies a positive storage control. It supplies neither a mod-material purge nor a transaction-specific server decision for the player's chisel recipe.

## Compatibility and independent review

Eight public-launcher cases exercised independently built API 1 and API 2 packages on a copy of a previously played dedicated world. Mixed packages, dependent removal, empty selection, reinstall, optional capability discovery and recovery all served and exited successfully. The altered target fingerprint and the required unavailable capability each stopped startup as expected. The recorded player and terrain payloads matched after every case. The physical client and native Solo runs above used the public launcher and independently compiled packages.

Separate reviewers recomputed the row-return comparisons, aligned the renderer call stacks to executable segments, checked the two distinct status-byte outcomes, and reconciled the clock events with ordinary logs and saved files. They also reproduced the occupied-store comparisons and checked catalogue admissions for duplicated entries. Three site-only storage intervals stayed outside the function count. One row sweep timed out, and a later high-slot run had a phase-recording race. Both were excluded from the paired-return totals. One exploratory Solo run did not finish the intended leave sequence and was excluded from the two-visit result. Two fresh-world console controls reached the observer’s timeout before it requested a normal stop because it expected a different save label. Their 60 autosaves are counted from actual native entries and game logs. Public CI runs original Innesto fixtures. Real-game findings come from controlled local installations.

## Proposed execution contract

The following are acceptance requirements for a future adapter. This release exposes no lifecycle C API.

- **Capability availability** belongs to a verified adapter for a physical image and supported logical role. Discovering a capability at mod initialization would allow a mod to subscribe. It would confer no permission to read a particular world.
- **Readiness** belongs to a live session. The host must publish the registry before the first permitted material query and separately establish when world or simulation objects become usable. A Solo visit creates a fresh session even if the client process survives.
- **Execution** must arrive on a host-owned context with an explicit logical role. The adapter may forward an already valid call synchronously. It needs an actual host scheduling interface before it can accept work from another thread.
- **Lifetime and shutdown** need a defined ordering. Close admission before teardown, cancel queued work, drain callbacks that have started, and invalidate session handles before destroying their objects. Reopening must reject a handle from the previous session. Copy query results for the mod or confine all borrowed state to the callback.
- **Acceptance** requires an independently compiled mod exercising stock and extended count, exact name, valid slot zero and a miss. Test premature, wrong-thread, after-stop, previous-session and unsupported-target requests. Confirm the game receives no native operation for rejected requests.

## Outstanding issues and next experiments

| Issue | Evidence still required |
| --- | --- |
| [#55 Native material queries](https://github.com/ImJstNickDev/Innesto/issues/55) | First priority. Obtain a permitted resolver and host-delivered, post-publication callback with an ordered end of admission. Exercise the independent mod on dedicated, then evaluate the physical client and genuine Solo child separately. |
| [#3 Block-break event](https://github.com/ImJstNickDev/Innesto/issues/3) | Locate the authoritative pre-removal decision with position, veto, ordered listeners and player correction. A simulation-loop observation supplies no decision operand. |
| [#36 Inventory authority](https://github.com/ImJstNickDev/Innesto/issues/36) | Pair one ordinary player craft with a server-originated acceptance, refusal or ingredient debit. The existing result, saved quantities and stock identity controls can anchor the comparison. |
| [#5 Custom crafting](https://github.com/ImJstNickDev/Innesto/issues/5) | Establish a supported registration phase, ownership of recipe and ingredient storage, peer visibility, authoritative payment and removal. Client-side growth can invalidate retained recipe rows. |
| [#45 Safe removal](https://github.com/ImJstNickDev/Innesto/issues/45) | Demonstrate a selective writer across unloaded terrain and all item-bearing stores using an occupied third-party stack. Verify backup, unrelated data, drops, reconnect, restart and reinstallation. |
| [#47 Natural generation](https://github.com/ImJstNickDev/Innesto/issues/47) | Find a rule input that the native generator consumes for third-party identities, or a permitted pre-persistence generation callback. Verify natural multiplayer harvest and stability of previously generated terrain. |
| [#4 Release acceptance](https://github.com/ImJstNickDev/Innesto/issues/4) | Reproduce a documented, decision-changing mod from a clean checkout and remove it on the actual game. |

After host delivery, prioritize the server crafting transaction and a positively identified mod-owned stack in an occupied store. Either can distinguish competing explanations without relying on a full world reconstruction. For generation, require evidence that the generator consumes a proposed rule before enlarging seed surveys. Access to an installed copy and authorization to test a local server establish the scope of these observations. A reviewed distribution basis for each mapping and a permitted execution interface are separate requirements. The outstanding technical gates above can be tested with ordinary game behavior and a cooperative host. No individual mapping received a distribution grant. The public changes extend catalogue import and filtering to lifecycle, assets, rendering and interface evidence. Original regression fixtures exercise those filters across catalogue revisions.
