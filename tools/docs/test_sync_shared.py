"""Exercise two maintainers publishing the same documentation sync."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import sync_shared


GAME = "game/one"
TOPIC = "sync/shared-docs/one"


class ConcurrentSyncTests(unittest.TestCase):
    def setUp(self):
        build = Path(__file__).resolve().parents[2] / "build"
        build.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=build)
        self.addCleanup(temp.cleanup)
        self.enterContext(contextlib.chdir(temp.name))
        self.enterContext(patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Test maintainer",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test maintainer",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }))
        self.git = sync_shared.git
        self.git("init", "-q", "-b", "main")
        self.git("init", "-q", "--bare", "remote.git")
        self.git("remote", "add", "origin", "remote.git")
        Path("README.md").write_text("previous")
        self.git("add", "README.md")
        self.git("commit", "-qm", "docs: add initial readme")
        self.git("push", "-q", "origin", f"HEAD:refs/heads/{GAME}")
        Path("README.md").write_text("current")
        self.git("commit", "-qam", "docs: refresh readme")
        self.source = self.git("rev-parse", "HEAD").decode().strip()

    def raced_create(self, *, same_repository):
        error = subprocess.CalledProcessError(1, "gh pr create")
        calls = []

        def github(*args, data=None):
            calls.append(args[0])
            self.assertEqual(args[args.index("--base") + 1], GAME)
            self.assertEqual(args[args.index("--head") + 1], TOPIC)
            if args[0] == "create":
                raise error
            rows = [] if calls == ["list"] else [
                {"isCrossRepository": not same_repository, "url": "matching-url"}
            ]
            return json.dumps(rows).encode()

        with patch.object(sync_shared, "github_pr", github):
            if same_repository:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    sync_shared.sync(GAME, self.source)
                self.assertIn("matching-url", output.getvalue())
            else:
                with self.assertRaises(subprocess.CalledProcessError) as raised:
                    sync_shared.sync(GAME, self.source)
                self.assertIs(raised.exception, error)
        self.assertEqual(calls, ["list", "create", "list"])

    def test_duplicate_pr_recovers_the_open_request(self):
        self.raced_create(same_repository=True)

    def test_create_error_with_only_a_fork_pr_still_fails(self):
        self.raced_create(same_repository=False)

    def raced_push(self, *, same_change):
        def git(*args, **kwargs):
            if args[0] == "push":
                commit, ref = args[-1].split(":")
                message = self.git("show", "-s", "--format=%B", commit).rstrip() + b"\n"
                if not same_change:
                    message = b"docs: preserve a manual edit\n"
                # A second maintainer reaches origin immediately before our push.
                other = self.git("commit-tree", f"{commit}^{{tree}}", "-p", f"{commit}^",
                                 data=message, env=dict(os.environ, GIT_AUTHOR_NAME="Other"))
                self.git("push", "-q", "origin", f"{other.decode().strip()}:{ref}")
            return self.git(*args, **kwargs)

        with patch.object(sync_shared, "git", git), patch.object(
            sync_shared, "open_pr", return_value="matching-url"
        ) as lookup:
            if same_change:
                sync_shared.sync(GAME, self.source)
                lookup.assert_called_once_with(TOPIC, GAME)
            else:
                with self.assertRaises(subprocess.CalledProcessError):
                    sync_shared.sync(GAME, self.source)
                lookup.assert_not_called()

    def test_racing_push_accepts_the_equivalent_managed_commit(self):
        self.raced_push(same_change=True)

    def test_racing_push_preserves_manually_authored_commit(self):
        self.raced_push(same_change=False)


if __name__ == "__main__":
    unittest.main()
