# Development guide

## Preview the documentation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git.
Clone the project and start the preview server.

```sh
git clone https://github.com/ImJstNickDev/Innesto.git
cd Innesto
uv run --project tools/docs --locked mkdocs serve
```

Open <http://127.0.0.1:8000/>. Edits under `docs/` reload the preview. The
documentation builds independently of any game installation.

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
version branch. The published site follows `main`. When a version is released,
link its tagged documentation from the compatibility table.

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
uv run --project tools/docs --locked mkdocs build --strict
```

CI builds the guide and reports broken internal documentation links as errors.
A merge to `main` publishes the guide on GitHub Pages. Changes to public behavior
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
