"""Exercise exact-build catalogs against two independently stripped, original ELF hosts."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HOSTS = [Path(arg).resolve() for arg in sys.argv[1:3]]
READELF = sys.argv[3]
del sys.argv[1:4]


class NativeMappings(unittest.TestCase):
    def run_host(self, host, case):
        recorded = [path.with_name(path.name + ".sha256").read_text().strip() for path in HOSTS]
        observed = hashlib.sha256(host.read_bytes()).hexdigest()
        result = subprocess.run([host, *recorded, observed, case], check=True, capture_output=True,
                                text=True, timeout=5)
        return result.stdout.splitlines()

    def test_fixture_images_are_actually_stripped(self):
        digests = [hashlib.sha256(host.read_bytes()).digest() for host in HOSTS]
        self.assertNotEqual(*digests)
        for host in HOSTS:
            with self.subTest(host=host):
                listing = subprocess.check_output([READELF, "-SW", host], text=True)
                self.assertIn(".dynsym", listing)
                self.assertNotIn(".symtab", listing)
                self.assertNotIn(".debug_", listing)
                exports = subprocess.check_output([READELF, "--dyn-syms", "--wide", host], text=True)
                self.assertNotRegex(exports, r"(owned_|innesto_native_)")

    def test_build_specific_layouts_and_two_independent_rules(self):
        expected = ["setup ok", "busy occupied", "original break 1", "break position -4,71,9",
                    "result 7", "block present=0", "original break 1", "break position 0,-20,63",
                    "result 0", "block present=1",
                    "original break 0", "result 0", "block present=0", "original inspect 1",
                    "inspect position 0,-20,63", "result 11", "original break 1", "result 7", "block present=0"]
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertEqual(self.run_host(host, "play"), expected)

    def test_unavailable_and_ambiguous_targets_leave_original_live(self):
        for host in HOSTS:
            for case, status in [
                ("version", "unavailable"), ("platform", "unavailable"), ("environment", "unavailable"),
                ("digest", "unavailable"), ("profile-twice", "ambiguous"), ("name-twice", "ambiguous"),
                ("slot-twice", "ambiguous"), ("missing-function", "unavailable"),
                ("missing-type", "unavailable"), ("wrong-kind", "incompatible"),
                ("wrong-operand", "incompatible"), ("missing-projector", "unavailable"),
                ("missing-original", "unavailable"), ("malformed-digest", "invalid"),
            ]:
                with self.subTest(host=host, case=case):
                    self.assertEqual(self.run_host(host, case),
                                     ["setup " + status, "original break 1", "result 7", "block present=0"])

    def test_same_version_rebuilt_bytes_need_a_new_mapping(self):
        with tempfile.TemporaryDirectory(dir=HOSTS[0].parent) as work:
            changed = Path(work) / "unrecognized-build"
            shutil.copy2(HOSTS[0], changed)
            with changed.open("ab") as stream:
                stream.write(b"rebuilt")
            self.assertEqual(self.run_host(changed, "play"),
                             ["setup unavailable", "original break 1", "result 7", "block present=0"])


if __name__ == "__main__":
    unittest.main()
