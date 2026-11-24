"""Linux native Solo companion verification and staging."""
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from adapters.a1_2_10.solo_host import LIFETIME, stage_solo_host, verify_host
from innesto_terrain import directory_lock


class SoloHost(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.client = root / "client"
        self.client.touch()
        self.host = root / "owserver"
        shutil.copy2(shutil.which("true"), self.host)
        self.digest = hashlib.sha256(self.host.read_bytes()).hexdigest()
        self.world = root / "world"
        self.world.mkdir()
        self.runtime = root / "runtime"
        self.runtime.mkdir()

    def test_stock_reference_requires_the_full_count_from_this_solo_session(self):
        from adapters.a1_2_10.solo_reference import stock_count
        log = self.runtime / "console"
        prefix = "2000-01-01 00:00:00 [INFO ] "
        banner = prefix + "[client] [t0] Openworld Client a1.2.10"
        child = prefix + f"[solo] [t0] child ({self.host})"
        ready = prefix + "[solo] [t0] OW-SOLO ready port=1 version=a1.2.10 protocol=1"
        hud = prefix + "[hud] [t0] example (7 materials, icons)"
        lod = prefix + "[lod] [t0] example (18 materials, terrain)"
        valid = [banner, child, ready, hud, lod]
        log.write_text("\n".join(valid))
        self.assertEqual(stock_count(log, self.host), 18)
        for lines in (valid[:-1], [banner, ready, hud, lod], [banner, child, hud, lod],
                      valid + [banner], valid + [lod.replace("18", "19")], ["Innesto example initialized", *valid]):
            log.write_text("\n".join(lines))
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                stock_count(log, self.host)

    def test_pinned_sibling_is_staged_byte_for_byte(self):
        self.assertEqual(verify_host(self.client, self.digest.upper()), self.digest)
        with directory_lock(self.world) as lease:
            with stage_solo_host(self.runtime, self.client, self.digest, self.world, lease):
                image = self.runtime / "owserver"
                self.assertEqual(image.read_bytes(), self.host.read_bytes())
                self.assertEqual(stat.S_IMODE(image.stat().st_mode), 0o500)
                self.assertTrue((self.runtime / LIFETIME).is_file())

    def test_image_changed_after_preflight(self):
        pin = verify_host(self.client, self.digest)
        shutil.copy2(shutil.which("cat"), self.host)
        with directory_lock(self.world) as lease, self.assertRaisesRegex(ValueError, "fingerprint"):
            with stage_solo_host(self.runtime, self.client, pin, self.world, lease):
                self.fail("changed host staged")

    def test_requires_private_fingerprint(self):
        for pin in (None, 1, "", "z" * 64, "0" * 64):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                verify_host(self.client, pin)

    def test_refuses_privileged_and_non_executable_images(self):
        self.host.chmod(0o4755)
        with self.assertRaisesRegex(ValueError, "privilege"):
            verify_host(self.client, self.digest)
        self.host.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "executable"):
            verify_host(self.client, self.digest)
        self.host.write_bytes(b"#! /bin/sh\n")
        self.host.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "format"):
            verify_host(self.client, hashlib.sha256(self.host.read_bytes()).hexdigest())

    def test_refuses_symlinks_and_special_files(self):
        self.host.unlink()
        self.host.symlink_to(shutil.which("true"))
        with self.assertRaises(OSError):
            verify_host(self.client, self.digest)
        self.host.unlink()
        os.mkfifo(self.host, 0o700)
        with self.assertRaisesRegex(ValueError, "regular executable"):
            verify_host(self.client, self.digest)

    def test_replaced_world_stays_outside_runtime(self):
        with directory_lock(self.world) as lease:
            self.world.rename(self.world.with_suffix(".old"))
            self.world.mkdir()
            with self.assertRaisesRegex(ValueError, "changed while locked"):
                with stage_solo_host(self.runtime, self.client, self.digest, self.world, lease):
                    self.fail("replaced world accepted")


if __name__ == "__main__":
    unittest.main()
