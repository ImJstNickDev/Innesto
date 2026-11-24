"""Original fixtures for the native Solo save view and its fresh-world transaction."""
import fcntl
import hashlib
import json
import os
import select
import time
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from adapters.a1_2_10 import terrain_solo as solo
from innesto_registry import Registry, REGISTRY


class SoloTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.world = self.root / "Forest"
        self.world.mkdir()
        self.lease = os.open(self.world, os.O_DIRECTORY)
        self.addCleanup(lambda: os.close(self.lease))
        self.game = self.root / "game"
        self.saves = self.game / "saves"
        self.other = self.saves / "unrelated"
        self.other.mkdir(parents=True)
        (self.other / "sentinel").write_bytes(b"original")
        self.args = ["--game-dir", str(self.game)]
        self.dig = hashlib.sha256(b"native").hexdigest()
        self.identity = dict(game="a1.2.10", platform="linux-x86_64",
                             stock=self.dig, baseCount=1, server=solo.identity_digest(self.dig, self.dig))

    def enroll(self):
        registry = Registry(self.lease, self.identity)
        definition = dict.fromkeys(("visual", "gameplay", "receipt", "visualPolicy"), self.dig)
        registry.accept({"test:material": definition})

    def test_fresh_and_restart_keep_native_metadata_and_role(self):
        solo.validate_world(self.lease, self.world)
        self.assertEqual(list(self.world.iterdir()), [])
        self.enroll()
        solo.prepare_world(self.lease, self.world)
        path = self.world / "world.json"
        data = json.loads(path.read_bytes())
        self.assertEqual((data["slug"], data["name"], data["game_mode"]), (solo.SLOT, "Forest", "survival"))
        self.assertTrue(data["seed"])
        original = path.read_bytes()
        solo.prepare_world(self.lease, self.world)
        self.assertEqual(path.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            Registry(self.lease, {**self.identity, "server": self.dig})
        data["game_mode"] = "creative"
        path.write_text(json.dumps(data))
        self.assertTrue(solo.validate_world(self.lease, self.world))
        self.assertEqual((data["worldgen_version"], data["data_format"]), (32, 1))
        for key, value in (("last_played_with", "a1.2.11"), ("worldgen_version", 99),
                           ("data_format", 2), ("data_format", True)):
            with self.subTest(field=key, value=value):
                path.write_text(json.dumps({**data, key: value}))
                with self.assertRaisesRegex(ValueError, "metadata"):
                    solo.validate_world(self.lease, self.world)
        data["slug"] = "../unrelated"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "metadata"):
            solo.validate_world(self.lease, self.world)
        self.assertEqual(json.loads(path.read_text()), data)

    def test_missing_metadata_never_adopts_a_populated_save(self):
        (self.world / "state").write_bytes(b"existing")
        with self.assertRaises(ValueError):
            solo.validate_world(self.lease, self.world)
        with self.assertRaises(ValueError):
            Registry(self.lease, self.identity)
        self.assertFalse((self.world / REGISTRY).exists())
        (self.world / "state").unlink()
        self.enroll()
        (self.world / "blocks").write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "metadata"):
            solo.prepare_world(self.lease, self.world)
        self.assertFalse((self.world / "world.json").exists())

    def test_metadata_creation_resumes_an_interrupted_first_launch(self):
        self.enroll()
        (self.world / solo.PENDING_METADATA).write_bytes(b'{"form')
        solo.prepare_world(self.lease, self.world)
        self.assertFalse((self.world / solo.PENDING_METADATA).exists())
        self.assertEqual(json.loads((self.world / "world.json").read_bytes())["slug"], solo.SLOT)

    def test_reject_ambiguous_arguments_and_hidden_inputs(self):
        self.assertEqual(solo.game_directory(self.world, self.args), self.game)
        for options in (["--play", "example"], ["--terrain-peer", "example"], ["--launch-ticket", "/x"],
                        ["--game-dir", "/second"], ["--play=example"], ["--game-dir=/second"],
                        ["--player-name", "--game-dir"], ["--unverified-mode"], ["--log-dir", str(self.other)]):
            with self.subTest(options=options), self.assertRaises(ValueError):
                solo.game_directory(self.world, self.args + options)
        for path in (self.saves, self.other, self.game):
            with self.subTest(world=path), self.assertRaises(ValueError):
                solo.game_directory(path, self.args)
        with self.assertRaises(ValueError):
            solo.game_directory(self.world, self.args, inputs=[self.other / "library"])
        for path in (self.root, self.world, self.world / "bootstrap.so"):
            with self.subTest(launcher_input=path), self.assertRaises(ValueError):
                solo.game_directory(self.world, self.args, inputs=[path])

    @unittest.skipUnless(shutil.which("bwrap"), "requires bubblewrap")
    def test_isolated_client_can_write_only_its_selected_save(self):
        check = subprocess.run(["bwrap", "--unshare-user", "--unshare-net", "--unshare-pid",
                                "--ro-bind", "/", "/", "true"], capture_output=True)
        if check.returncode:
            self.skipTest("kernel does not permit the Solo mount and network namespaces")
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "solo-lifetime").touch()
        code = """
import errno, os, pathlib, sys
game = pathlib.Path(sys.argv[sys.argv.index('--game-dir')+1])
saves = game/'saves'
assert [p.name for p in saves.iterdir()] == ['innesto-solo']
(saves/'innesto-solo'/'persistent').write_bytes(b'saved')
assert os.stat(saves/'innesto-solo').st_ino == os.fstat(int(os.environ['INNESTO_WORLD_LEASE_FD'])).st_ino
assert os.environ['INNESTO_INIT_PID'] == str(os.getpid())
assert set(p.name for p in pathlib.Path('/sys/class/net').iterdir()) >= {'lo'}
assert {line.split(':')[0].strip() for line in pathlib.Path('/proc/net/dev').read_text().splitlines() if ':' in line} == {'lo'}
try: (saves/'second').mkdir()
except OSError as exc: assert exc.errno == errno.EROFS
else: raise AssertionError('created an extra save')
"""
        image = os.open(sys.executable, os.O_RDONLY)
        try:
            pid = os.fork()
            if pid == 0:
                try:
                    env = {**os.environ, "INNESTO_WORLD_LEASE_FD": str(self.lease)}
                    os.set_inheritable(self.lease, True)
                    solo.exec_in_view(self.world, self.lease, self.game, runtime, image, sys.executable,
                                      ["-B", "-c", code, *self.args], env)
                finally:
                    os._exit(111)
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        finally:
            os.close(image)
        self.assertEqual((self.world / "persistent").read_bytes(), b"saved")
        self.assertEqual((self.other / "sentinel").read_bytes(), b"original")
        self.assertEqual(list(self.saves.iterdir()), [self.other])

    @unittest.skipUnless(shutil.which("bwrap"), "requires bubblewrap")
    def test_orphaned_native_host_keeps_save_until_its_final_write(self):
        check = subprocess.run(["bwrap", "--unshare-user", "--unshare-net", "--unshare-pid",
                                "--ro-bind", "/", "/", "true"], capture_output=True)
        if check.returncode:
            self.skipTest("kernel does not permit the Solo mount and network namespaces")
        runtime = self.root / "runtime"
        runtime.mkdir()
        lifetime = runtime / "solo-lifetime"
        lifetime.touch()
        fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ready_r, ready_w = os.pipe()
        done_r, done_w = os.pipe()
        image = os.open(sys.executable, os.O_RDONLY)
        code = """
import os, signal, sys
from pathlib import Path
if os.fork() == 0:
    os.close(int(os.environ['INNESTO_WORLD_LEASE_FD']))
    os.write(int(sys.argv[1]), b'H')
    assert os.read(int(sys.argv[2]), 1) == b'S'
    (Path(sys.argv[4])/'saves/innesto-solo/final').write_bytes(b'saved')
    os._exit(0)
os.kill(os.getpid(), signal.SIGKILL)
"""
        pid = os.fork()
        if pid == 0:
            try:
                os.close(ready_r)
                os.close(done_w)
                for fd in (ready_w, done_r, self.lease):
                    os.set_inheritable(fd, True)
                env = {**os.environ, "INNESTO_WORLD_LEASE_FD": str(self.lease)}
                solo.exec_in_view(self.world, self.lease, self.game, runtime, image, sys.executable,
                                  ["-B", "-c", code, str(ready_w), str(done_r), *self.args], env)
            finally:
                os._exit(111)
        os.close(ready_w)
        os.close(done_r)
        os.close(image)
        try:
            self.assertTrue(select.select([ready_r], [], [], 5)[0], "logical host failed to start")
            self.assertEqual(os.read(ready_r, 1), b"H")
            # Release the original parent reference and use a fresh description
            # to observe the lock held exclusively by the game namespace.
            os.close(self.lease)
            self.lease = os.open(self.world, os.O_DIRECTORY)
            with self.assertRaises(BlockingIOError):
                fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with lifetime.open("r+") as guard:
                with self.assertRaises(BlockingIOError):
                    fcntl.lockf(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.write(done_w, b"S")
        finally:
            os.close(done_w)
            os.close(ready_r)
            os.waitpid(pid, 0)
        with lifetime.open("r+") as guard:
            fcntl.lockf(guard, fcntl.LOCK_EX)
        self.assertEqual((self.world / "final").read_bytes(), b"saved")
        deadline = time.monotonic() + 5
        while True:
            try:
                fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self.fail("logical host lease remained locked after exit")
                time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
