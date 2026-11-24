"""Build the shared documentation and the guides owned by each game branch."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def git(*args):
    return subprocess.check_output(["git", "-C", ROOT, *args])


def version_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError(f"Invalid game version {name!r}")
    return name


def game_branches():
    for prefix in ("refs/remotes/origin/game/", "refs/heads/game/"):
        lines = git("for-each-ref", "--format=%(refname) %(objectname)", prefix).decode()
        if lines:
            branches = {}
            for line in lines.splitlines():
                ref, commit = line.split()
                branches[version_name(ref.removeprefix(prefix))] = commit
            return branches
    return {}


def worktree_files(directory):
    # Include new guides during preview, while respecting the checkout's ignore rules.
    paths = git("ls-files", "-co", "--exclude-standard", "-z", "--", directory)
    for raw in paths.split(b"\0"):
        if not raw:
            continue
        name = Path(os.fsdecode(raw))
        path = ROOT / name
        if any((ROOT / item).is_symlink() for item in (name, *name.parents)):
            raise ValueError(f"Documentation cannot be a symbolic link: {name}")
        if path.is_file():
            yield name, path.read_bytes()


def committed_files(commit, directory):
    entries = git("ls-tree", "-rz", "--full-tree", commit, "--", directory)
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        meta, raw_name = entry.split(b"\t", 1)
        mode, kind, oid = meta.split()
        name = Path(os.fsdecode(raw_name))
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError(f"Expected a regular documentation file: {name}")
        yield name, git("cat-file", "blob", oid.decode())


def copy_docs(directory, commit, target, *, shared=False):
    files = committed_files(commit, directory) if commit else worktree_files(directory)
    for name, contents in files:
        relative = name.relative_to(directory)
        if ".." in relative.parts or not relative.parts:
            raise ValueError(f"Invalid documentation path: {name}")
        if shared and relative.parts[0] in {"version", "versions"}:
            raise ValueError(f"Shared docs use the reserved directory {name}")
        path = target / relative
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(contents)


def on_config(config):
    """MkDocs hook; reassemble the same inputs on each live preview rebuild."""
    stage = Path(config.config_file_path).parent
    if stage.parent != ROOT / "build" or not stage.name.startswith("docs-"):
        raise ValueError("Run the documentation builder through tools/docs/site.py")
    docs = stage / "docs"
    shutil.rmtree(docs)
    docs.mkdir()
    game = os.environ["INNESTO_DOCS_GAME"]
    copy_docs("docs", "refs/remotes/origin/main" if game else None, docs, shared=True)

    branches = game_branches()
    if game:
        branches[game] = None  # Build the worktree, including uncommitted guide edits.
    if not branches:
        raise ValueError("No game branches found. Fetch the game/* branches from origin.")

    versions = sorted(branches)
    navigation = [{"All versions": "versions/index.md"}]
    for version in versions:
        dest = docs / "versions" / version
        copy_docs("docs/version", branches[version], dest)
        if not (dest / "index.md").is_file():
            raise ValueError(f"Missing docs/version/index.md for game/{version}")
        pages = sorted(dest.rglob("*.md"))
        pages.remove(dest / "index.md")
        pages.insert(0, dest / "index.md")
        navigation.append({version: [p.relative_to(docs).as_posix() for p in pages]})

    catalog = [
        "# Game versions", "",
        "Choose your Openworld version for platform support, build instructions and mod examples.",
        "", *(f"- [Openworld {version}]({version}/index.md)" for version in versions),
    ]
    (docs / "versions/index.md").write_text("\n".join(catalog) + "\n", encoding="utf-8")

    if config.nav is not None:
        config.nav = [*config.nav, {"Versions": navigation}]
    return config


def on_serve(server, *, config, builder):
    # Watch the editable sources. Watching the staged copies would trigger a rebuild loop.
    server.unwatch(config.docs_dir)
    if os.environ["INNESTO_DOCS_GAME"]:
        server.watch(str(ROOT / "docs/version"))
    else:
        server.watch(str(ROOT / "docs"))
        server.watch(str(ROOT / "mkdocs.yml"))
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "serve"])
    parser.add_argument("--game", metavar="VERSION", help="use docs/version from this worktree")
    args = parser.parse_args()

    branch = git("branch", "--show-current").decode().strip()
    game = args.game or (branch[5:] if branch.startswith("game/") else "")
    if game:
        version_name(game)
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="docs-", dir=build) as tmp:
        stage = Path(tmp)
        (stage / "docs").mkdir()
        shared_config = ROOT / "mkdocs.yml"
        if game:
            shared_config = stage / "shared.yml"
            configs = list(committed_files("refs/remotes/origin/main", "mkdocs.yml"))
            if not configs:
                raise ValueError("Missing mkdocs.yml on origin/main")
            shared_config.write_bytes(configs[0][1])

        config = stage / "mkdocs.yml"
        config.write_text(json.dumps({
            "INHERIT": str(shared_config),
            "docs_dir": str(stage / "docs"),
            "site_dir": str(ROOT / "site"),
            "edit_uri": "",
            "hooks": [str(Path(__file__).resolve())],
        }), encoding="utf-8")
        env = dict(os.environ, INNESTO_DOCS_GAME=game, TMPDIR=tmp, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, "-m", "mkdocs", args.command, "--strict", "-f", str(config)],
            cwd=ROOT,
            env=env,
        ).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
