"""Exercise the optional dedicated-server save reader through the public launcher."""
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(sys.argv.pop(1)).resolve()
CC = sys.argv.pop(1)
PLAYER = "01234567-89ab-cdef-0123-456789abcdef"


class SavedBlocks(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=BUILD)
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.records = self.work / "records"
        self.records.mkdir()
        self.target = BUILD / "innesto-test-host"
        self.digest = hashlib.sha256(self.target.read_bytes()).hexdigest()
        self.profile = self.work / "target.json"
        self.profile.write_text(json.dumps(dict(version="a1.2.10", platform="linux-x86_64",
                                                executable=str(self.target), sha256=self.digest)))
        self.mapping = dict(serverSha256=self.digest, directory=str(self.records), revision=7,
                            fields=dict(revision="schema", player="owner", broken="removed", placed="added"))
        package = self.work / "packages" / "query"
        package.mkdir(parents=True)
        (package / "innesto.mod.json").write_text(json.dumps(dict(
            schemaVersion=1, id="query", version="1.0.0", game="a1.2.10", api=2,
            environment="shared", entrypoint="query.so")))
        subprocess.run([CC, "-shared", "-fPIC", "-I", ROOT / "include", ROOT / "tests/saved_blocks_probe.c",
                        "-o", package / "query.so"], check=True)

    def launch(self, *, configured=True, client=False):
        env = os.environ.copy()
        env.pop("INNESTO_SAVED_BLOCKS_BINDING", None)
        if configured:
            path = self.work / "mapping.json"
            path.write_text(json.dumps(self.mapping))
            env["INNESTO_SAVED_BLOCKS_BINDING"] = str(path)
        if client:
            data = json.loads(self.profile.read_text())
            self.profile.write_text(json.dumps(dict(data, environment="client")))
        return subprocess.Popen([ROOT / "tools/innesto-run", "--profile", self.profile,
                                 "--loader", BUILD / "innesto-bootstrap.so", "--mods-dir", self.work / "packages"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, text=True)

    def test_binding_available(self):
        with self.launch() as proc:
            stdout, stderr = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 0, stderr)
            self.assertIn("binding available", stdout.splitlines())

    def test_gating(self):
        valid = self.mapping.copy()
        for options, patch in [
            (dict(configured=False), {}), ({}, {"serverSha256": "0" * 64}),
            ({}, {"directory": str(self.work / "missing")}), ({}, {"revision": "7"}),
            ({}, {"fields": dict(valid["fields"], broken="added")}),
            ({}, {"fields": dict(valid["fields"], broken="")}), (dict(client=True), {}),
        ]:
            with self.subTest(options=options, patch=patch):
                self.mapping = dict(valid, **patch)
                with self.launch(**options) as proc:
                    stdout, stderr = proc.communicate(timeout=10)
                    self.assertEqual(proc.returncode, 0, stderr)
                    self.assertIn("binding absent", stdout.splitlines())

    def test_queries_and_replacement(self):
        record = self.records / (PLAYER + ".json")
        valid = dict(schema=7, owner=PLAYER, removed=0, added=3)
        with self.launch() as proc:
            def line():
                self.assertTrue(select.select([proc.stdout], [], [], 5)[0], "query timed out")
                return proc.stdout.readline().strip()

            def query(id, expected):
                proc.stdin.write(id + "\n")
                proc.stdin.flush()
                self.assertEqual(line(), expected)

            try:
                self.assertEqual(line(), "binding available")
                query(PLAYER, "2 22 33")
                for bad in ("null-id", "null-output", "../" + PLAYER, PLAYER.upper(), ""):
                    query(bad, "1 22 33")
                record.write_text(json.dumps(valid))
                query(PLAYER, "0 0 3")
                replacement = self.records / "replacement"
                replacement.write_text(json.dumps(dict(valid, removed=2**40, added=0)))
                replacement.replace(record)
                query(PLAYER, f"0 {2**40} 0")
                for patch in (dict(owner="other"), dict(schema=8), dict(schema=True),
                              dict(removed=-1), dict(removed=1.5), dict(added=False), dict(added="0")):
                    record.write_text(json.dumps(dict(valid, **patch)))
                    query(PLAYER, "4 22 33")
                for raw in ('{"removed": 1, "removed": 2}', '{}', 'null', '[]', '{', json.dumps(valid) + 'x'):
                    record.write_text(raw)
                    query(PLAYER, "4 22 33")
                replacement.write_text(json.dumps(valid))
                record.unlink()
                record.symlink_to(replacement)
                query(PLAYER, "3 22 33")
                record.unlink()
                os.mkfifo(record)
                query(PLAYER, "3 22 33")
                record.unlink()
                query(PLAYER, "2 22 33")
            finally:
                proc.stdin.close()
                if proc.poll() is None:
                    proc.wait(timeout=5)
            self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
