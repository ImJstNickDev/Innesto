"""Check and propagate the shared parts of the Innesto documentation."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


SHARED_PATHS = (
    "README.md",
    "CONTRIBUTING.md",
    "mkdocs.yml",
    "docs/",
    ":(exclude)docs/version/**",
    "tools/docs/",
    ".github/workflows/documentation.yml",
    ".github/workflows/publish-docs.yml",
    ".github/workflows/shared-docs.yml",
)


def run(*args, data=None, env=None):
    return subprocess.run(
        args, input=data, stdout=subprocess.PIPE, env=env, check=True
    ).stdout


def git(*args, **kwargs):
    return run("git", *args, **kwargs)


def shared_diff(base, source):
    return git("diff", "--no-renames", "--name-only", "-z", base, source, "--", *SHARED_PATHS)


def branches():
    refs = git("for-each-ref", "--format=%(refname)", "refs/remotes/origin/game/")
    return [os.fsdecode(ref).removeprefix("refs/remotes/origin/") for ref in refs.splitlines()]


def report(ref, changed):
    names = [os.fsdecode(path) for path in changed.split(b"\0") if path]
    if names:
        print(f"{ref} differs in {len(names)} shared paths:", flush=True)
        for name in names:
            print(f"  {name!r}", flush=True)
    else:
        print(f"{ref} is current.", flush=True)


def check(args):
    refs = [f"origin/{branch}" for branch in branches()] if args.all else [args.ref]
    current = True
    for ref in refs:
        changed = shared_diff(ref, args.source)
        report(ref, changed)
        current = current and not changed
    return 0 if current else 1


def ancestor(older, newer):
    result = subprocess.run(["git", "merge-base", "--is-ancestor", older, newer])
    if result.returncode not in (0, 1):
        result.check_returncode()
    return result.returncode == 0


def shared_tree(base, source, changed):
    # An independent index keeps the user's working tree and staged changes intact.
    git_dir = os.fsdecode(git("rev-parse", "--absolute-git-dir").rstrip(b"\n"))
    with tempfile.TemporaryDirectory(prefix="shared-docs-", dir=git_dir) as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        git("read-tree", base, env=env)
        git("--literal-pathspecs", "restore", "--staged", f"--source={source}",
            "--pathspec-from-file=-", "--pathspec-file-nul", data=changed, env=env)
        return git("write-tree", env=env).decode().strip()


def github_pr(*args, data=None):
    # gh's default repository can differ from the remote receiving the Git push.
    origin = os.fsdecode(git("remote", "get-url", "origin").rstrip(b"\n"))
    return run("gh", "pr", *args, env=dict(os.environ, GH_REPO=origin), data=data)


def open_pr(topic, game):
    result = github_pr("list", "--state", "open", "--base", game, "--head", topic,
                       "--json", "url,isCrossRepository")
    return next((pr["url"] for pr in json.loads(result) if not pr["isCrossRepository"]), None)


def sync(game, source):
    base = git("rev-parse", "--verify", f"refs/remotes/origin/{game}^{{commit}}").decode().strip()
    changed = shared_diff(base, source)
    report(game, changed)
    topic = f"sync/shared-docs/{game.removeprefix('game/')}"
    ref = f"refs/remotes/origin/{topic}"
    old = git("for-each-ref", "--format=%(objectname) %(refname)", ref).decode().splitlines()
    previous = next((row.split()[0] for row in old if row.split()[1] == ref), None)
    trailer = f"Innesto-Docs-Target: {game}"

    if previous:
        # A maintainer may have added work to the topic. Leave it for review.
        messages = git("log", "--format=%B%x00", previous, "--not", base).split(b"\0")
        if any(os.fsencode(trailer) not in msg.splitlines() for msg in messages if msg.strip()):
            raise ValueError(f"{topic} contains manually authored work; inspect the branch first.")

    if not changed:
        if previous and (url := open_pr(topic, game)):
            github_pr("close", url)
            print(f"Closed superseded sync request {url}")
        return

    tree = shared_tree(base, source, changed)
    if previous and ancestor(base, previous):
        parents = ["-p", previous]
    elif previous and not ancestor(previous, base):
        # Join the old sync topic and the new target without rewriting history.
        parents = ["-p", previous, "-p", base]
    else:
        parents = ["-p", base]
    if not previous or parents != ["-p", previous] or (
        git("rev-parse", f"{previous}^{{tree}}").decode().strip() != tree
    ):
        message = f"docs: sync shared documentation for {game}\n\n{trailer}\n"
        commit = git("commit-tree", tree, *parents, data=message.encode()).decode().strip()
        if shared_diff(commit, source):
            raise ValueError(f"Shared-path verification failed for {game}.")
        git("push", "origin", f"{commit}:refs/heads/{topic}")

    url = open_pr(topic, game)
    if not url:
        body = (
            f"Copy the shared documentation from main ({source[:12]}) into `{game}`. "
            "The version guide and game code come from the target branch.\n\n"
            "Verification: the sync command compared the shared Git trees before pushing. "
            "The documentation and native checks run on the pull request."
        )
        url = github_pr("create", "--base", game, "--head", topic,
                        "--title", f"docs: sync shared documentation for {game}",
                        "--body-file", "-", data=body.encode()).decode().strip()
    print(f"{game}: {url}", flush=True)


def pull_requests(args):
    git("fetch", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*")
    source = git("rev-parse", "--verify", "refs/remotes/origin/main^{commit}").decode().strip()
    targets = branches()
    if args.game:
        if args.game not in targets:
            raise ValueError(f"Unknown game branch on origin: {args.game!r}")
        targets = [args.game]
    failed = False
    for game in targets:
        try:
            sync(game, source)
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            retry = shlex.join(["python3", "tools/docs/sync_shared.py", "pr", "--game", game])
            print(f"{game}: {exc}\nMaintainer recovery: {retry}", file=sys.stderr)
            failed = True
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("check", help="compare shared files using local Git refs")
    compare.add_argument("--source", default="origin/main")
    target = compare.add_mutually_exclusive_group()
    target.add_argument("--ref", default="HEAD")
    target.add_argument("--all", action="store_true", help="check all fetched origin/game/* branches")
    publish = commands.add_parser("pr", help="open or refresh documentation sync pull requests")
    target = publish.add_mutually_exclusive_group(required=True)
    target.add_argument("--game", metavar="game/VERSION")
    target.add_argument("--all", action="store_true")
    args = parser.parse_args()
    try:
        # Run pathspecs from the repository root even when invoked from a subdirectory.
        os.chdir(os.fsdecode(git("rev-parse", "--show-toplevel").rstrip(b"\n")))
        return check(args) if args.command == "check" else pull_requests(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
