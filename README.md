<p align="center">
  <img src="docs/assets/innesto.svg" width="76" height="76" alt="" />
</p>

<h1 align="center">Innesto</h1>
<p align="center"><strong>Native mods for Openworld.</strong></p>
<p align="center">
  <a href="https://imjstnickdev.github.io/Innesto/">Documentation</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="https://github.com/ImJstNickDev/Innesto/milestone/1">First release milestone</a>
</p>

Innesto is an independent native mod loader and C API for Openworld. Mods
are built against a specific game version. Each version guide lists the
client and server capabilities that have been verified for that build.

Find build instructions, supported features and examples in the
[guide for your Openworld version](https://imjstnickdev.github.io/Innesto/versions/).

## Work on the documentation

Preview the guide from the repository root using [uv](https://docs.astral.sh/uv/).

```sh
git fetch origin --prune
uv run --project tools/docs --locked python tools/docs/site.py serve
```

Open <http://127.0.0.1:8000/> to preview edits. Build the guide with strict validation before opening a pull request.

```sh
uv run --project tools/docs --locked python tools/docs/site.py build
```

The [development guide](docs/development.md) covers branches, pull requests
and releases. The [API conventions](docs/api-conventions.md) describe what a
mod author should learn from the docs for each new feature.

Innesto is distributed under the [MIT License](LICENSE).
