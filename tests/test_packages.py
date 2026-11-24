"""Validate package discovery, dependency ordering and the launcher handoff."""

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from innesto_packages import MANIFEST, discover_mods

LAUNCHER = TOOLS / "innesto-run"


class PackageTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "build"
        scratch.mkdir(exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(directory.cleanup)
        self.scratch = Path(directory.name)
        self.mods = self.scratch / "mods"
        self.mods.mkdir()

    def package(self, name, folder=None, **overrides):
        manifest = {
            "schemaVersion": 1, "id": name, "version": "1.2.3", "game": "a1.2.10",
            "api": 1, "environment": "server", "entrypoint": "lib/module.so",
            **overrides,
        }
        directory = self.mods / (folder or name)
        library = directory / "lib/module.so"
        library.parent.mkdir(parents=True)
        library.touch()
        (directory / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        return library

    def refused(self, *messages):
        with self.assertRaises(ValueError) as caught:
            discover_mods(self.mods)
        for message in messages:
            self.assertIn(message, str(caught.exception))

    def test_guide_contains_the_installed_observer_manifest(self):
        source = (ROOT / "docs/version/mod-packages.md").read_text(encoding="utf-8")
        example = json.loads((ROOT / "examples/observer" / MANIFEST).read_text(encoding="utf-8"))
        blocks = [part.split("\n```", 1)[0] for part in source.split("```json\n")[1:]]
        self.assertIn(example, [json.loads(block) for block in blocks])

    def test_empty_directory_and_loose_files(self):
        (self.mods / "ignored.file").touch()
        (self.mods / "dangling").symlink_to("absent")
        self.assertEqual(discover_mods(self.mods), [])
        self.mods = self.scratch / "absent"
        self.refused("existing directory")

    def test_each_package_directory_requires_a_manifest(self):
        (self.mods / "unpacked").mkdir()
        self.refused("unpacked", MANIFEST)

    def test_stable_order_by_available_id(self):
        last = self.package("z", "01-independent")
        dependent = self.package("a", "02-dependent", depends={"m": "1.2.3"})
        first = self.package("m", "03-first")
        final = self.package("consumer", depends={"z": "*", "a": "*"})
        self.assertEqual(discover_mods(self.mods), [first, dependent, last, final])

    def test_duplicate_keys_are_errors_at_both_levels(self):
        self.package("sample")
        file = self.mods / "sample" / MANIFEST
        original = file.read_text()
        for fragment, key in [('"id": "other"', "id"), ('"depends": {"a": "*", "a": "*"}', "a")]:
            with self.subTest(key=key):
                file.write_text(original[:-1] + ", " + fragment + "}")
                self.refused(f"duplicate key '{key}'")

    def test_malformed_manifest_and_schema(self):
        self.package("sample")
        file = self.mods / "sample" / MANIFEST
        original = json.loads(file.read_text())
        for content, message in [
            (b"\xff", "decode"), (b"{", "property"), (b"[]", "object"), (b"{}", "missing"),
        ]:
            with self.subTest(content=content):
                file.write_bytes(content)
                self.refused("sample", message)
        bad_fields = {
            "schemaVersion": [True, 1.0, 2],
            "id": ["Upper", "9sample", "foo.bar", "àbc", None],
            "version": [0, "01.2.3", "1.02.3", "1.2.03", "1.2", "1.2.3-rc", "1.2.٣"],
            "game": ["other"], "api": [True, "1", 2], "environment": ["client"],
            "entrypoint": [None, "", "lib/absent.so", "lib", "/absolute", "../escape"],
            "depends": [[], None], "typo": ["value"],
        }
        for key, values in bad_fields.items():
            for value in values:
                with self.subTest(field=key, value=value):
                    file.write_text(json.dumps({**original, key: value}))
                    self.refused("sample", key)
        for dep in [{"Bad": "*"}, {"mod": "^1.0.0"}, {"mod": 2}]:
            with self.subTest(dep=dep):
                file.write_text(json.dumps({**original, "depends": dep}))
                self.refused("dependency")

    def test_duplicate_ids_and_files(self):
        first = self.package("sample", "one")
        self.package("sample", "two")
        self.refused("duplicate mod id", "sample", "one", "two")
        file = self.mods / "two" / MANIFEST
        file.write_text(json.dumps({**json.loads(file.read_text()), "id": "another"}))
        second = self.mods / "two/lib/module.so"
        second.unlink()
        os.link(first, second)
        self.refused("same entrypoint file", "sample", "another")

    def test_missing_and_mismatched_dependencies(self):
        self.package("sample", depends={"helper": "1.0.1"})
        self.refused("sample", "missing mod", "helper")
        self.package("helper")
        self.refused("sample", "helper", "1.0.1", "1.2.3")

    def test_cycle_reports_the_connected_mod_ids(self):
        self.package("aaa", depends={"b": "*"})
        self.package("b", depends={"c": "*"})
        self.package("c", depends={"b": "*"})
        self.refused("cycle", "b -> c -> b")

    def test_package_and_files_must_stay_in_their_respective_directories(self):
        library = self.package("sample")
        directory = self.mods / "sample"
        outside = self.scratch / "outside"
        outside.mkdir()
        alias = self.mods / "alias"
        alias.symlink_to(outside)
        self.refused("alias", "outside")
        alias.unlink()
        outside_library = outside / library.name
        library.rename(outside_library)
        library.symlink_to(outside_library)
        self.refused("entrypoint", "inside")
        library.unlink()
        inside_library = directory / "inside.so"
        inside_library.touch()
        library.symlink_to(inside_library)
        self.assertEqual(discover_mods(self.mods), [inside_library])
        manifest = directory / MANIFEST
        outside_manifest = outside / MANIFEST
        manifest.rename(outside_manifest)
        manifest.symlink_to(outside_manifest)
        self.refused(MANIFEST, "inside")

    def test_memfd_contains_nul_terminated_filesystem_bytes(self):
        mod_list = runpy.run_path(str(LAUNCHER))["mod_list"]
        libraries = [self.mods / os.fsdecode(b"\xff\n :module.so"), self.mods / "last.so"]
        with mod_list(libraries) as plan:
            self.assertGreaterEqual(plan.fileno(), 3)
            self.assertFalse(os.get_inheritable(plan.fileno()))
            self.assertEqual(plan.read(), b"".join(os.fsencode(path) + b"\0" for path in libraries))
        with mod_list([]) as plan:
            self.assertEqual(plan.read(), b"")

    def test_cli_requires_exactly_one_mod_source(self):
        for args in [[], ["--mod", "library", "--mods-dir", "mods"]]:
            with self.subTest(args=args):
                result = subprocess.run(
                    [LAUNCHER, "--profile", "profile", "--loader", "loader", *args],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("--mods-dir", result.stderr)


if __name__ == "__main__":
    unittest.main()
