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

Innesto is an independent mod loader and API project for Openworld. The loader
will initialize mods inside the game process. The API will give authors a shared
way to change game behavior and define how multiple mods interact.

The first development target is **Openworld a1.2.10 on Linux x86-64**. Work is at
the repository foundation stage. The first playable milestone is a separately
built mod that can veto a block break through the public API.

## Work on the documentation

Preview the guide from the repository root using [uv](https://docs.astral.sh/uv/).

```sh
uv run --project tools/docs --locked mkdocs serve
```

Open <http://127.0.0.1:8000/> to preview edits. Build the guide with strict validation before opening a pull request.

```sh
uv run --project tools/docs --locked mkdocs build --strict
```

The [development guide](docs/development.md) covers branches, pull requests
and releases. The [API conventions](docs/api-conventions.md) describe what a
mod author should learn from the docs for each new feature.

Innesto is distributed under the [MIT License](LICENSE).
