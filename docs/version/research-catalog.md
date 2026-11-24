# Research catalogue for a1.2.10

The private research catalogue answers three questions for an exact game build. Which interface was observed? Which evidence supports that interpretation? What still stops an adapter from using it? The launcher and mod API have no dependency on the catalogue.

The [lifecycle and gameplay study](native-lifecycle-study.md) reports revision 6, including execution phases, material rows, occupied stores and the remaining requirements for each gameplay issue.

## Find a result or a missing prerequisite

Run the commands below from the checkout. The evidence root is the directory against which the private snapshot's relative paths were recorded. SQLite and Python 3.11 or later are sufficient to query the catalogue.

```sh
tool=tools/research/catalog.py
db=.private/atlas/catalog.sqlite
python3 "$tool" history "$db"
python3 "$tool" search "$db" --subsystem inventory
python3 "$tool" search "$db" --kind function --role dedicated
python3 "$tool" needs "$db" --issue 3
python3 "$tool" files "$db" verification --limit 20
```

Use `show DB KEY` to see the exact claim, its limits, native candidate, signature status, type notes, supporting files and related records. A semantic name can occur in several images or in more than one candidate. The client, dedicated server and bundled Solo host have separate roles, even when two installed binaries contain identical bytes. A match between identical copies establishes shared code identity. It does not independently establish what that code does in either role.

## Record and reproduce an observation

Keep projects, logs, binaries, private inputs and the SQLite file outside public Git history. The portable snapshot is JSON. Each revision includes the game and platform, a digest per studied role, a manifest of SHA-256 evidence receipts, records, relationships and issue prerequisites. Private machine addresses belong only to function records. Each signature has its own state. The catalogue can record an unknown signature even when the surrounding behavior is well established.

```sh
python3 "$tool" import "$db" "$snapshot" --root .private
python3 "$tool" verify "$db" --root .private
python3 "$tool" snapshot "$db" --revision 1 > "$private_replay_file"
```

Import checks each evidence file and commits a complete revision atomically. Reimporting an identical revision is safe. Correcting a claim requires the next revision. Archive manifests index historical paths and hashes without moving or copying the original files. `verify --archived` also rehashes every indexed historical regular file. Keep the evidence tree with the database when moving it. A database backup preserves the observations and receipts. Keep the original evidence files for replay.

| State | Meaning |
| --- | --- |
| Discovered | An artifact, function candidate or observable surface exists in this build. |
| Inferred | The evidence supports an interpretation. The record identifies what could disprove it. |
| Verified | Independent evidence supports the precise claim on the specified role. Scope and remaining unknowns still apply. |

Record confidence separately from state. A high-confidence candidate can still have an unknown calling convention. Track the issue's missing prerequisite even when a related observable behavior is verified. A save containing a crafted item, for example, establishes persistence. Determining which side validated the ingredient debit takes separate evidence.

## Findings and outstanding gameplay dependencies

The initial a1.2.10 study covered three installed roles and two distinct executable images. Of 63 client–dedicated comparisons in the selected sample, independent checks supported three correspondences. Two further pairs remain candidates. The short terrain descriptor routine matched in both images and was sampled during dedicated catalogue loading. The native signature and its execution on the client remain open questions.

At 25 sampled terrain columns, material and elevation agreed between the seed inspector and the live world at every corresponding centre. A shifted alignment matched at most 11. In a Solo crafting sequence, the saved inventory already contained the crafted tool one checkpoint before the game saved its discovery. These controls give the generation and crafting investigations reproducible ways to check output.

### Material lookup, saved stacks and crafting

The follow-up catalogue tracks 60 unique game functions across the two images, up from 13. A function is counted once per executable and entry. The 41 semantic names include homologous functions under a shared name. Dedicated and Solo execution observations retain their own roles. Nine function records have independent evidence for their stated purpose. Three dedicated records have a verified machine contract within the documented calling conditions.

| Operation | Evidence from the installed dedicated server | Boundary for an adapter |
| --- | --- | --- |
| Count initialized material slots | A standalone generator check returned 435 on the stock catalogue. Adding 8,192 rows made the same operation return 8,627 in a second standalone check. Independent server catalogues agreed with both values. | Count includes stock, reserved and empty-material slots. First initialization and teardown have a separate lifecycle. |
| Resolve an exact material name | A valid zero-slot name and a missing name both returned zero. The accompanying success flag distinguished them. Changing the case of a known name produced a miss. A stock material’s lookup name and its dashboard key also gave different results. | A lookup API needs an explicit success result and a documented name space. The confirmed caller ran on the dedicated main thread with writable result storage. |
| Normalize a saved item code | During player-save reads in two isolated dedicated processes, the same alternative code normalized to the canonical value in both hotbar and bag. The canonical input stayed unchanged. Static analysis accounted for the other return paths. | This converts a code. Stack quantity, ownership and crafting authorization belong to separate operations. |

Twelve isolated server boots tested when the active material roster is chosen. In eight crossover boots the staged descriptor on disk changed after startup. Sixteen subsequent dashboard reads still showed the original IDs and properties. Sixteen operator placements independently resolved the original IDs. Separate fresh boots with the changed descriptor confirmed that it did change the roster. For these ordinary operations, prepare the complete descriptor before launch.

On the client, the crafting grid consumes a stock recipe collection. Stock result counts agreed with an archived Survival craft. During two player crafting intervals, the dedicated server logged inventory saves. The component responsible for approving the ingredient debit remains unknown. The existing recipe-registration and authority gates below still apply.

### Can a mod query the live material registry?

On the dedicated server, an independently compiled API 2 mod paused at its
initializer and again at its startup-complete callback. Both ran on the
process leader with logical side unknown. A separate observer found the native
registry uninitialized at all eight checkpoints across four launches. Once
the server was serving its world, the observed slot counts were 435 in both
stock runs and 8,627 in both extended runs. The game's own catalogue agreed
on each run. The mod made zero native material calls.

The installed executables provide no material accessor through their dynamic
symbol tables. The operator's exact-name lookups ran on the server's main
thread. Dashboard row reads ran on a secondary thread and exercised a
different operation. A binding still needs a reviewed way to resolve the slot
count and exact-name lookup for the exact image and to call them while the registry is live,
with a verified thread and shutdown contract. The physical client has its own
image. Solo runs a separate host process and needs independent delivery there.

A future lookup contract must return success separately from the numeric slot.
AIR succeeds at slot zero and a miss also returns zero. The input is the
native lookup name. A pack key can differ from that name, and an Innesto
identifier belongs to the persistent world registry. [Material API acceptance](https://github.com/ImJstNickDev/Innesto/issues/55)

The bounded crafting follow-up identified two further client functions,
bringing the inventory to 62 unique functions and 43 semantic names. On the
checked stock paths the client owns the recipe rows and their ingredient
storage. Growing the collection can invalidate a row address. The two new
functions have static evidence and unknown calling contracts. Identifying
which side approves an ingredient debit still requires transaction evidence.

| Issue | Evidence still required |
| --- | --- |
| [#3](https://github.com/ImJstNickDev/Innesto/issues/3) | A mod controls the authoritative pre-break decision, with ordered listeners, correct drops, feedback and reconnect behavior. |
| [#4](https://github.com/ImJstNickDev/Innesto/issues/4) | An independently built mod changes a real decision through the documented installation and removal workflow. |
| [#5](https://github.com/ImJstNickDev/Innesto/issues/5) | The server accepts a mod-defined recipe that the client displays and that disappears on removal. |
| [#36](https://github.com/ImJstNickDev/Innesto/issues/36) | An independent observation identifies server validation or ingredient debit for the crafting transaction. |
| [#45](https://github.com/ImJstNickDev/Innesto/issues/45) | A selective purge covers all occupied stores and terrain, with recovery, reconnect and reinstall controls. |
| [#47](https://github.com/ImJstNickDev/Innesto/issues/47) | A mod-defined rule generates naturally harvestable material while preserving populated terrain and peer compatibility. |

## From a finding to a binding

1. Identify a semantic operation in a subsystem. Keep the measured behavior, the candidate function and any cross-image correspondence in separate records linked by explicit relationships.
2. Confirm the operation on each supported role using independent evidence. For a callable interface, establish the native signature, operand type, lifetime, execution context and failure behavior. Similarity scores and inferred prototypes do not satisfy this requirement.
3. Review each distributable identifier and typed mapping against the exact snapshot. Record the reviewer and the distribution basis for each selection in a separate private review document. A semantic-only grant can publish an Innesto identifier. A binding grant also requires a verified declaration of a supported cooperative slot. The catalogue accepts the canonical prototypes `int(opaque const*)` for a rule and `position(opaque const*)` for a position projection.
4. Export the reviewed fields, inspect the diff and submit the original declaration and its tests through a PR. Pair the result privately with the reviewed image before use. The native adapter checks the exact profile, expected kind and operand before a hook or typed projection can be installed. Advertise the high-level capability only after the binding succeeds and the actual game meets its acceptance criteria. [Native mapping adapter](native-mappings.md)

```sh
python3 "$tool" export "$db" "$private_review" --root .private > "$candidate_export"
```

Exports use the checksummed snapshot document and a field allowlist. A stale review, changed evidence, unverified record, ambiguous identifier or slot, or missing typed declaration stops the export. The result contains reviewed semantic IDs, roles and any approved cooperative slot kinds and numbers. Keep binary fingerprints, locations, private signatures, type notes, evidence and review records in the private workspace. A successful export is a review candidate; distribution requires an individual licensing and provenance decision.

## Methodology

AnyPS5 separates observations of a caller from measurements of the implementation and records which questions the evidence can settle. LeviLamina separates symbol and hook facilities from typed event emission. Fabric API's block-break contract distinguishes the logical server, cancellation and post-action notification. Innesto uses these distinctions to keep evidence, adaptation and mod-facing behavior independently testable. [AnyPS5 research methodology](https://github.com/boykopovar/AnyPS5/blob/5f04682cef1e1c7f46162773b6a92a6fa49dd59a/docs/dev/REVERSE_ENGINEERING.md) · [LeviLamina event implementation](https://github.com/LiteLDev/LeviLamina/blob/922ff2e83cd3bccae56970d325cc3669344d8117/src/ll/api/event/player/PlayerDestroyBlockEvent.cpp) · [Fabric API event contract](https://github.com/FabricMC/fabric-api/blob/495da79f62942fa2630b576ce2075536d37b8223/fabric-events-interaction-v0/src/main/java/net/fabricmc/fabric/api/event/player/PlayerBlockBreakEvents.java)

## Run the original analysis fixtures

The scoped inventory starts from an explicit ELF and an operator-selected set of data strings. It intersects candidate references with x86-64 unwind ranges. Headless Ghidra checks the selected bodies; PyGhidra can reopen the saved project and check the target identity and function entries. An interval can describe just part of a native function. A role remains attached to its installed image throughout the analysis.

Use a fresh work directory for each command. With an installed Ghidra 12.2 distribution, a compatible JDK, GNU binutils, a C compiler and the distribution's PyGhidra package:

```sh
python3 tools/research/ghidra/fixture.py \
  --work "$work/inventory" --headless "$GHIDRA_INSTALL_DIR/support/analyzeHeadless" --pyghidra
python3 tools/research/matching/check_fixture.py \
  --ghidra "$GHIDRA_INSTALL_DIR" --output "$work/matching"
```

The matching fixture compares selected functions in two independently compiled stripped binaries. BSim ranks the selected pairs; Version Tracking runs exact correlators over the same selection. The fixture separately executes known inputs against the original programs. Changing a constant can change program output while leaving the structural match intact. Inspect the alternative candidates and record any independent evidence before assigning a semantic ID. [Ghidra BSim tutorial](https://ghidra.re/ghidra_docs/GhidraClass/BSim/README.html)

## Snapshot and review documents

A format-1 snapshot contains `revision`, `game`, `platform`, `targets` (role to private image digest), `artifacts` (evidence path to digest), `records`, `links` and `needs`. Optional `archives` names pinned JSON-lines manifests. Each indexed regular file has `kind: "file"`, a relative path, size and SHA-256; the manifest retains symlink and exclusion notes separately.

A record requires a unique `key`, a `semantic` ID, role, subsystem, kind, state, confidence, claim, limits and one or more evidence entries. Each evidence entry names a pinned path and its method. Two method labels alone do not establish independence. The maintainer must explain what the second observation actually tests. Use `entry` for a private ELF address and `signature_state` for the separate assessment of a native prototype. `types` holds type observations. A link connects two record keys. A prerequisite names an issue, a record key and what that issue still requires. [Executable catalogue examples](https://github.com/ImJstNickDev/Innesto/blob/game/a1.2.10/tests/test_research_catalog.py)

A review document specifies `format: 1`, the integer `revision`, the exact `snapshot` digest printed by import, a `reviewer` and a list of `grants`. Each grant names one record `key`, a `mode` of `semantic` or `binding`, and its distribution `basis`. Review the evidence and entitlement for each proposed grant before signing off in the PR.

To prepare a cooperative binding for a local adapter, verify that the installation, role and exported document all agree with the review. This output **is private** and contains the exact image digest.

```sh
umask 077
python3 "$tool" private-profile "$db" "$private_review" --root .private \
  --role dedicated --image "$local_executable" --mappings "$candidate_export" > "$private_profile"
```

The original native regression takes the reviewed rule and position slots through the existing C adapter, checks the image identity, binds the typed projection and exercises the decision. A changed executable, different role or edited public document fails before profile generation. The adapter's cooperative declaration is a property of that fixture. Distributed game research needs its own verified resolution and invocation evidence.
