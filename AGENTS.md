# Maintaining Innesto

Innesto is an independent native mod loader and C API for Openworld. Work on
the current game line, `game/a1.2.10`, targets Linux x86-64. Keep shared
bootstrap and package behavior usable by both the physical client and the
dedicated server. A logical server may run inside a client process.

## Where changes belong

- Target `main` for branding, shared guides, these instructions and documentation
  tooling. The shared-document workflow carries them to the game branch.
- Target the game branch for loader code, version adapters, mappings, API
  contracts, independent examples, native tests and `docs/version/`.
- Keep game-specific types and binding details behind the version adapter.
  Public mod contracts use a versioned C ABI. Determine capability availability
  from an installed adapter for the verified target.
- Use a focused issue with testable acceptance criteria and a Conventional
  Commit PR title. Check the target branch, open PRs and shared-file sync
  before editing. Review the diff and CI results before squash-merging.

## Interoperability research

Use a legitimately obtained local installation and limit observations to what
the interface requires. Respect the game's terms. Work in a private checkout
directory such as `.private/`; keep original files read-only and use isolated
state for runtime tests. Preserve the identity of the inputs and the steps
needed to repeat each observation in the private record.

Publish Innesto's original source, contracts, original fixtures and sanitized
results. Review mapping data individually for necessity and distributability.
Keep vendor download metadata, binaries, assets, fingerprints, decompiled
material, game internals and raw observations out of Git, issues, logs attached
to PRs and CI artifacts. Use original fixtures in public CI. Leave licensing,
authentication, integrity and anti-cheat mechanisms intact. Run game tests
against local installations and servers under the tester's control.

## Acceptance and releases

Exercise the public launcher and independently built mods. Verify unsupported
builds, unavailable capabilities and legacy server packages. Record the
physical environment and distinguish process initialization, gameplay
observations and fixture results.

Update the version guide alongside every change to a mod-facing contract.
Keep gameplay issues open until all their real-game acceptance steps pass.
The `a1.2.10-v0.1.0` milestone requires a documented mod to change a decision
in the actual game before a prerelease can be tagged.
