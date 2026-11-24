# Development guide

## Preview the documentation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git.
Clone the project and start the preview server.

```sh
git clone https://github.com/ImJstNickDev/Innesto.git
cd Innesto
git fetch origin --prune
uv run --project tools/docs --locked python tools/docs/site.py serve
```

Open <http://127.0.0.1:8000/>. The site combines the shared guide and each fetched game
branch’s `docs/version/` pages. The documentation builds independently of any
game installation.

## Choose a branch

| Change | Pull request base |
| --- | --- |
| Project workflow, branding or shared documentation | `main` |
| Loader, API, examples or docs for Openworld a1.2.10 | `game/a1.2.10` |

Create a short-lived branch from its intended base. A documentation branch for the shared API writing guide starts from `main`.

```sh
git switch -c docs/api-guide origin/main
```

Use a descriptive prefix such as `feat/`, `fix/` or `docs/`. Keep game-specific
examples and reference documentation alongside the implementation on its
version branch. Write version-specific pages in `docs/version/`, with `index.md`
as their starting page. When you create a `game/<version>` branch with that
index, the next site build adds it to the [version catalog](versions/index.md)
and publishes its guide at `versions/<version>/`. When
working on a feature branch for a game version, preview its local pages with
`python tools/docs/site.py serve --game a1.2.10` in the documentation environment.

`main` owns the shared README, branding, contributor guides and documentation
tooling. To change one of those files, target `main`. After a merge, the sync
workflow checks active game branches and prepares pull requests for shared
changes. Version-specific code and guides stay on the game branch. If GitHub
puts a workflow run for an Actions-created sync PR on hold, review its diff,
approve the run and wait for the required checks to pass before merging.

A game branch PR must pass the shared-file check. To recover a stale branch,
fetch the latest refs and run `python3 tools/docs/sync_shared.py pr --game game/a1.2.10`
with an authenticated GitHub CLI. Merge the synchronization PR through the
usual checks, then update any pending feature branch. Use the same command
when Actions lacks permission to copy a changed workflow or open its PR.

## Submit a change

Use Conventional Commits for commits and PR titles. A title such as
`fix(loader): report duplicate mod IDs before initialization` identifies both
the affected component and the observable change. The PR title becomes the
squash commit title.

Include the reason for the change, its effect on mod authors, implementation
details needed for review, and the commands and outcomes you verified. Link
the corresponding issue when one exists. For a version branch PR, check that
the issue closes when the work is complete. GitHub's automatic closing keywords
operate on the default branch.

Run the documentation check from the root of the checkout.

```sh
uv run --project tools/docs --locked python tools/docs/site.py build
```

CI builds the guide and reports broken internal documentation links as errors.
A successful push build on `main` or a game branch triggers a full site
publication from the current branch tips. Changes to public behavior
must update the version's reference and example in the same PR.

## Public and private material

Publish Innesto source, mod contracts, original examples, supported version and
platform, and sanitized results. Keep game files, distribution metadata, build
fingerprints, symbols and internal investigation records in private maintainer
storage. Review screenshots, logs, diffs and attachments before sharing them.
Use original fixtures in public CI.

## Release a version

Use a tag of the form `<game-version>-v<semver>` on the tested game branch.
The first planned tag is `a1.2.10-v0.1.0`. Publish it as a GitHub prerelease
after an independent mod can be built, loaded, exercised and removed by
following the public guide. Include the supported version and platform,
user-visible changes, setup instructions and a link to the tagged source.
