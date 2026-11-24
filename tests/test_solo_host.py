"""Linux native Solo companion verification and staging."""
import fcntl
import hashlib
import os
from pathlib import Path
import select
import shutil
import signal
import time
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from adapters.a1_2_10.solo_host import LIFETIME, stage_solo_host, verify_host
from innesto_terrain import directory_lock, run_supervised


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

    def test_supervisor_forwards_signals_until_orphan_host_finishes(self):
        # Model the GUI closing before the namespace releases its lifetime lock.
        ready, notify = os.pipe()
        prompt, release = os.pipe()
        path = self.runtime / LIFETIME
        supervisor = os.fork()
        if supervisor == 0:
            try:
                os.close(ready)
                os.close(release)
                with path.open("wb+") as lifetime:
                    def launcher():
                        gui_signal, host_signal = os.pipe()
                        if os.fork() == 0:
                            os.close(gui_signal)
                            with path.open("rb") as record:
                                fcntl.lockf(record, fcntl.LOCK_SH)
                                signal.signal(signal.SIGINT, lambda *_: os.write(notify, b"S"))
                                os.write(host_signal, b"R")
                                os.write(notify, b"H")
                                os._exit(0 if os.read(prompt, 1) == b"Q" else 1)
                        os.close(host_signal)
                        os.read(gui_signal, 1)
                        os._exit(0)
                    code = run_supervised(launcher, namespace_lifetime=lifetime)
                    os._exit(code)
            finally:
                os._exit(1)
        os.close(prompt)
        os.close(notify)
        try:
            self.assertTrue(select.select([ready], [], [], 5)[0])
            self.assertEqual(os.read(ready, 1), b"H")
            # The supervisor has reaped its immediate child but is still
            # protecting the host. Signals must reach that process group.
            children = Path(f"/proc/{supervisor}/task/{supervisor}/children")
            for _ in range(500):
                if not children.read_text().strip():
                    break
                time.sleep(0.01)
            self.assertFalse(children.read_text().strip())
            os.kill(supervisor, signal.SIGINT)
            self.assertTrue(select.select([ready], [], [], 5)[0])
            self.assertEqual(os.read(ready, 1), b"S")
        finally:
            os.write(release, b"Q")
            os.close(release)
            os.close(ready)
            _, status = os.waitpid(supervisor, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)

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
