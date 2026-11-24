"""Check that invalid profiles stop the launcher before any native code runs."""

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[1] / "tools" / "innesto-run"


class TargetValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build = LAUNCHER.parents[1] / "build"
        build.mkdir(exist_ok=True)
        cls.workspace = tempfile.TemporaryDirectory(dir=build)
        cls.addClassCleanup(cls.workspace.cleanup)
        fixture = Path(cls.workspace.name) / "host"
        subprocess.run(
            ["cc", "-x", "c", "-", "-o", str(fixture)],
            input="int main(void) { return 0; }", text=True, check=True,
            env={**os.environ, "TMPDIR": cls.workspace.name},
        )
        cls.fixture_bytes = fixture.read_bytes()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=self.workspace.name)
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.target = self.root / "test executable"
        self.target.write_bytes(self.fixture_bytes)
        self.target.chmod(0o700)
        self.profile = {
            "executable": str(self.target),
            "version": "a1.2.10",
            "platform": "linux-x86_64",
            "sha256": hashlib.sha256(self.target.read_bytes()).hexdigest(),
        }

    def assert_refused(self, reason, loader=None, mod=None):
        path = self.root / "test-profile.json"
        path.write_text(json.dumps(self.profile), encoding="utf-8")
        missing_module = self.root / "not-built.so"
        result = subprocess.run(
            [sys.executable, str(LAUNCHER), "--profile", str(path),
             "--loader", str(loader or missing_module), "--mod", str(mod or missing_module)],
            capture_output=True, text=True, timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(reason, result.stderr)
        self.assertNotIn(str(self.root), result.stderr)

    def test_unrecognized_target_version(self):
        self.profile["version"] = "unsupported"
        self.assert_refused("unsupported target")

    def test_other_platform_in_profile(self):
        self.profile["platform"] = "unsupported"
        self.assert_refused("unsupported target")

    def test_hash_mismatch_stops_before_opening_loader(self):
        self.profile["sha256"] = "0" * 64
        self.assert_refused("unsupported target")

    def test_relative_target_path(self):
        self.profile["executable"] = "test executable"
        self.assert_refused("absolute")

    def test_matching_hash_does_not_admit_script(self):
        self.target.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.profile["sha256"] = hashlib.sha256(self.target.read_bytes()).hexdigest()
        self.assert_refused("unsupported target")

    def test_matching_hash_does_not_admit_foreign_interpreter(self):
        executable = bytearray(self.target.read_bytes())
        original = b"ld-linux-x86-64.so.2"
        self.assertIn(original, executable)
        executable = executable.replace(original, b"x" * len(original))
        self.target.write_bytes(executable)
        self.profile["sha256"] = hashlib.sha256(executable).hexdigest()
        self.assert_refused("unsupported target")

    def test_wrong_library_rejected_even_with_valid_target(self):
        other_library = self.root / "mod.so"
        subprocess.run(
            ["cc", "-x", "c", "-", "-fPIC", "-shared", "-o", str(other_library)],
            input="int fixture(void) { return 0; }", text=True, check=True,
            env={**os.environ, "TMPDIR": str(self.root)},
        )
        (self.root / "innesto-bootstrap.sha256").write_text("0" * 64 + "\n")
        self.assert_refused("bootstrap", loader=other_library, mod=other_library)

    def test_matching_hash_does_not_admit_static_target(self):
        executable = bytearray(self.target.read_bytes())
        start = struct.unpack_from("<Q", executable, 32)[0]
        stride, count = struct.unpack_from("<HH", executable, 54)
        for offset in range(start, start + count * stride, stride):
            if struct.unpack_from("<I", executable, offset)[0] == 3:
                struct.pack_into("<I", executable, offset, 0)
        self.target.write_bytes(executable)
        self.profile["sha256"] = hashlib.sha256(executable).hexdigest()
        self.assert_refused("unsupported target")


if __name__ == "__main__":
    unittest.main()
