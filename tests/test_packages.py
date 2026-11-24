"""Validate package discovery, dependency ordering and the launcher handoff."""

import hashlib
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
from innesto_packages import MANIFEST, SelectedMod, discover_mods, select_packages

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

    def terrain_package(self, name, folder=None):
        content = {"version": 1, "assets": "assets",
                   "terrain": [{"id": f"{name}:ore", "texture": "tiles/ore.png"}]}
        library = self.package(name, folder=folder, environment="shared", content=content)
        directory = library.parent.parent
        tile = directory / "assets/tiles/ore.png"
        tile.parent.mkdir(parents=True)
        tile.touch()
        return directory, tile

    def test_shared_terrain_belongs_to_its_package_on_both_sides(self):
        _, second_tile = self.terrain_package("zinc", "00-first")
        first, first_tile = self.terrain_package("copper", "99-last")
        first_tile.rename(first_tile.with_name("veined.png"))
        first_tile.symlink_to("veined.png")
        manifest = first / MANIFEST
        data = json.loads(manifest.read_text())
        data["content"]["terrain"].append({"id": "copper:alloy_2-a", "texture": "tiles/ore.png"})
        manifest.write_text(json.dumps(data))
        self.package("legacy")
        for side in ("client", "server"):
            mods = select_packages(self.mods, side)
            materials = {mod.mod_id: [(item.id, item.texture) for item in mod.terrain] for mod in mods}
            expected = {"copper": [("copper:ore", first_tile.resolve()),
                                   ("copper:alloy_2-a", first_tile.resolve())],
                        "zinc": [("zinc:ore", second_tile)]}
            if side == "server":
                expected["legacy"] = []
            self.assertEqual(materials, expected)
            self.assertTrue(all(isinstance(mod.terrain, tuple) for mod in mods))

    def test_v2_terrain_traits_are_typed_and_v1_stays_strict(self):
        directory, _ = self.terrain_package("copper")
        path = directory / MANIFEST
        data = json.loads(path.read_text())
        content = data["content"]
        tile = content["terrain"][0]
        tile.update(family="plant", tileMeters=0.5)
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "unknown field"):
            select_packages(self.mods, "client")
        content["version"] = 2
        path.write_text(json.dumps(data))
        material, = select_packages(self.mods, "server")[0].terrain
        self.assertEqual((material.family, material.tile_meters), ("plant", 0.5))
        for key, value in (("family", "unregistered"), ("family", ["plant"]),
                           ("tileMeters", True), ("tileMeters", 0), ("tileMeters", "0.5"),
                           ("tileMeters", float("nan")), ("tileMeters", {})):
            with self.subTest(key=key, value=value):
                content["terrain"] = [{**tile, key: value}]
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, key):
                    select_packages(self.mods, "server")

    def test_content_schema_and_material_identifiers(self):
        directory, _ = self.terrain_package("copper")
        manifest = directory / MANIFEST
        base = json.loads(manifest.read_text())
        content = base["content"]
        tile = content["terrain"][0]
        invalid = [
            (None, "content"), ({}, "version"), ({**content, "version": True}, "version"),
            ({**content, "version": 1.0}, "version"), ({**content, "version": 3}, "version"),
            ({**content, "unexpected": 1}, "unexpected"),
            ({"version": 1, "terrain": [tile]}, "assets"),
            ({"version": 1, "assets": "assets"}, "terrain"),
            ({**content, "terrain": {}}, "terrain"),
            ({**content, "terrain": [None]}, "terrain"),
            ({**content, "terrain": [{"id": "copper:ore"}]}, "texture"),
            ({**content, "terrain": [{**tile, "other": 3}]}, "other"),
            ({**content, "terrain": [tile, tile]}, "duplicate"),
        ]
        for material_id in ("ore", "other:ore", "copper:", "copper:UP", "copper:1ore",
                            "copper:ore/one", "copper:..", "copper:x:y", "copper:é", None):
            invalid.append(({**content, "terrain": [{**tile, "id": material_id}]}, "id"))
        for value, message in invalid:
            with self.subTest(value=value):
                manifest.write_text(json.dumps({**base, "content": value}))
                self.refused("copper", message)
        for side in ("server", "client"):
            with self.subTest(side=side):
                manifest.write_text(json.dumps({**base, "environment": side}))
                self.refused("shared")
        nested_duplicate = json.dumps(base).replace('"texture":', '"texture": "first.png", "texture":')
        manifest.write_text(nested_duplicate)
        self.refused("duplicate key", "texture")

    def test_asset_directory_and_texture_confinement(self):
        directory, tile = self.terrain_package("copper")
        manifest = directory / MANIFEST
        base = json.loads(manifest.read_text())
        content = base["content"]
        (directory / "assets/linked").symlink_to(directory / "lib", target_is_directory=True)
        (directory / "other-assets").symlink_to(self.scratch)
        (directory / "root-alias").symlink_to(directory)
        (self.scratch / "external.png").touch()
        (tile.parent / "external.png").symlink_to(self.scratch / "external.png")
        for field, paths in (
            ("assets", [None, "", ".", "root-alias", "absent", "assets/tiles/ore.png",
                        "../copper/assets", str(tile.parent), "other-assets"]),
            ("texture", [None, "", "absent.png", "tiles", "tiles/../tiles/ore.png",
                         str(tile), "linked/module.so", "tiles/external.png"]),
        ):
            for path in paths:
                with self.subTest(field=field, path=path):
                    bad = dict(content)
                    if field == "assets":
                        bad[field] = path
                    else:
                        bad["terrain"] = [{"id": "copper:ore", "texture": path}]
                    manifest.write_text(json.dumps({**base, "content": bad}))
                    self.refused("copper", field)

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
            "game": ["other"], "api": [True, "1", 3], "environment": ["integrated", "both"],
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
        mods = [SelectedMod(path, f"test{i}", i + 1) for i, path in enumerate(libraries)]
        digest = "a" * 64
        with mod_list("server", digest, mods) as plan:
            self.assertGreaterEqual(plan.fileno(), 3)
            self.assertFalse(os.get_inheritable(plan.fileno()))
            self.assertEqual(plan.read(), b"Innesto/3\0server\0" + digest.encode() + b"\0" + b"1\0test0\0" +
                             os.fsencode(libraries[0]) + b"\0" + b"2\0test1\0" +
                             os.fsencode(libraries[1]) + b"\0")
        with mod_list("client", digest, []) as plan:
            self.assertEqual(plan.read(), b"Innesto/3\0client\0" + digest.encode() + b"\0")

    def test_both_cli_modes_check_resolved_paths_for_glibc_tokens_before_launch(self):
        host = self.scratch / "host"
        subprocess.run(["cc", "-x", "c", "-", "-o", host], input=b"int main(void) { return 0; }",
                       env={**os.environ, "TMPDIR": str(self.scratch)}, check=True)
        profile = self.scratch / "profile.json"
        profile.write_text(json.dumps({"version": "a1.2.10", "platform": "linux-x86_64",
                                       "executable": str(host), "sha256": hashlib.sha256(host.read_bytes()).hexdigest()}))
        library = self.package("sample")
        # Keep CLI and manifest paths constant. Only the resolved target's parent changes.
        library.unlink()
        invalid = ["$ORIGIN", "one$LIB", "${PLATFORM}tail", "$PLATFORM-", "$$ORIGIN", "$LIBé"]
        valid = ["$HOME", "$ORIGINAL", "$LIB2", "$PLATFORM_", "${LIBS}", "${LIB", "$5"]
        for name in invalid + valid:
            target = library.parent / name / "module.so"
            target.parent.mkdir()
            target.touch()
            library.symlink_to(target)
            for choice in (["--mod", library], ["--mods-dir", self.mods]):
                with self.subTest(name=name, option=choice[0]):
                    # Supplying an executable as the loader identifies reaching
                    # the next validation stage without starting any native code.
                    result = subprocess.run([LAUNCHER, "--profile", profile, "--loader", host, *choice],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    if name in invalid:
                        self.assertIn("dynamic loader token", result.stderr)
                        self.assertIn(repr(name), result.stderr)
                        self.assertIn("rename", result.stderr)
                    else:
                        self.assertIn("loader must be a Linux x86-64 shared library", result.stderr)
            library.unlink()

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
