"""Exercise the assembled site against independent main and game histories."""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).with_name("site.py").resolve()


class SiteTests(unittest.TestCase):
    def setUp(self):
        build = TOOL.parents[2] / "build"
        build.mkdir(exist_ok=True)
        workspace = tempfile.TemporaryDirectory(dir=build)
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "docs@example.invalid")
        self.git("config", "user.name", "Documentation tests")
        self.write("mkdocs.yml", "site_name: Test\nnav:\n  - Home: index.md\n")
        self.write("docs/index.md", "# Shared from main\n\n[Guide](versions/one/index.md)\n")
        self.write("docs/assets/brand.txt", "current mark")
        self.commit()
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("switch", "-qc", "game/one")
        self.write("docs/index.md", "# Obsolete shared copy")
        self.write("docs/assets/brand.txt", "old mark")
        self.write("docs/version/index.md", "# Version one\n\n[Guide](startup.md)")
        self.write("docs/version/startup.md", "# Shipped guide")
        self.commit()
        self.git("update-ref", "refs/remotes/origin/game/one", "HEAD")
        self.git("switch", "-q", "main")
        (self.root / "tools/docs").mkdir(parents=True)
        shutil.copyfile(TOOL, self.root / "tools/docs/site.py")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=True)

    def write(self, path, contents):
        target = self.root / path
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_text(contents)

    def commit(self):
        self.git("add", "docs", "mkdocs.yml")
        self.git("commit", "-qm", "docs: add fixture pages")

    def build(self, *args, success=True):
        result = subprocess.run(
            [sys.executable, "tools/docs/site.py", "build", *args],
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stdout)
        return result.stdout

    def test_main_uses_remote_versions_and_shared_worktree(self):
        self.git("update-ref", "refs/heads/game/one", "main")
        self.git("update-ref", "refs/remotes/origin/game/two", "origin/game/one")
        self.write("docs/assets/brand.txt", "worktree mark")
        self.build()
        self.assertEqual((self.root / "site/assets/brand.txt").read_text(), "worktree mark")
        catalog = (self.root / "site/versions/index.html").read_text()
        links = re.findall(r'<a href="([^"]+)">Openworld ([^<]+)</a>', catalog)
        self.assertEqual(links, [("one/", "one"), ("two/", "two")])
        for version in ("one", "two"):
            self.assertTrue((self.root / f"site/versions/{version}/index.html").is_file())
            page = self.root / f"site/versions/{version}/startup/index.html"
            self.assertIn("Shipped guide", page.read_text())

    def test_game_preview_overlays_uncommitted_guides_and_uses_main_brand(self):
        self.git("switch", "-qc", "feat/new-guide", "origin/game/one")
        self.write("docs/version/draft.md", "# Worktree guide")
        self.build("--game", "one")
        self.assertEqual((self.root / "site/assets/brand.txt").read_text(), "current mark")
        page = self.root / "site/versions/one/draft/index.html"
        self.assertIn("Worktree guide", page.read_text())
        self.assertIn("Shared from main", (self.root / "site/index.html").read_text())

    def test_incomplete_game_or_symlink_fails_the_build(self):
        self.git("switch", "-q", "game/one")
        (self.root / "docs/version/index.md").unlink()
        self.assertIn("Missing docs/version/index.md", self.build(success=False))
        (self.root / "docs/version/index.md").symlink_to("../index.md")
        self.assertIn("symbolic link", self.build(success=False))

    def test_version_names_cannot_escape_staging(self):
        self.assertIn("Invalid game version", self.build("--game", "../escape", success=False))


if __name__ == "__main__":
    unittest.main()
