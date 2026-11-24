"""Exercise the public launcher with native fixtures and independent mod packages."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(sys.argv.pop(1)).resolve()
CC = sys.argv.pop(1)
LAUNCHER = ROOT / "tools/innesto-run"


class NativeInitialization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="innesto test ", dir=BUILD)
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        cls.packages = cls.work / "installed mods"
        for name in ("hello", "observer"):
            project = cls.work / f"standalone {name}"
            subprocess.run(["cmake", "-S", ROOT / "examples" / name, "-B", project,
                            f"-DCMAKE_C_COMPILER={CC}", f"-DINNESTO_INCLUDE_DIR={ROOT / 'include'}"],
                           check=True)
            subprocess.run(["cmake", "--build", project], check=True)
            subprocess.run(["cmake", "--install", project, "--prefix", cls.packages], check=True)
        cls.mod = cls.packages / "hello/innesto-hello.so"
        host = BUILD / "innesto-test-host"
        cls.profile = {"version": "a1.2.10", "platform": "linux-x86_64",
                       "executable": str(host), "sha256": hashlib.sha256(host.read_bytes()).hexdigest()}

    def launch(self, *args, profile=None, mod=None, mods_dir=None, loader=None, prior=None, pass_fds=()):
        config = self.work / "fixture.json"
        config.write_text(json.dumps(self.profile if profile is None else profile))
        env = {k: v for k, v in os.environ.items() if not k.startswith("INNESTO_") and k != "LD_PRELOAD"}
        env["INNESTO_MOD_PATH"] = "stale single-mod context"
        if prior:
            env["LD_PRELOAD"] = str(prior)
        selected = ["--mods-dir", mods_dir] if mods_dir else ["--mod", mod or self.mod]
        with subprocess.Popen([LAUNCHER, "--profile", config, "--loader", loader or BUILD / "innesto-bootstrap.so",
                               *selected, "--", *args],
                              cwd=self.work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, pass_fds=pass_fds) as proc:
            stdout, stderr = proc.communicate(timeout=10)
            return proc.returncode, proc.pid, stdout, stderr

    def copy_packages(self):
        directory = tempfile.TemporaryDirectory(dir=self.work)
        self.addCleanup(directory.cleanup)
        return shutil.copytree(self.packages, Path(directory.name) / "mods")

    def test_packages_initialize_in_dependency_order_and_can_be_removed(self):
        packages = self.copy_packages()
        for expected in (["hello", "observer"], ["hello"], []):
            with self.subTest(expected=expected):
                status, pid, stdout, stderr = self.launch("--reexec", mods_dir=packages)
                self.assertEqual(status, 0, stderr)
                self.assertIn("argument=child", stdout)
                markers = re.findall(r"Innesto (\w+) initialized \(pid=(\d+)\)", stderr)
                self.assertEqual(markers, [(name, str(pid)) for name in expected])
                if expected:
                    shutil.rmtree(packages / expected[-1])

    def test_invalid_later_manifest_prevents_all_initializers(self):
        packages = self.copy_packages()
        manifest = packages / "observer/innesto.mod.json"
        manifest.write_text(json.dumps({**json.loads(manifest.read_text()), "schemaVersion": 42}))
        status, _, stdout, stderr = self.launch(mods_dir=packages)
        self.assertNotEqual(status, 0)
        self.assertNotIn("host pid=", stdout)
        self.assertNotIn("initialized (pid=", stderr)
        self.assertIn("schema", stderr.lower())

    def test_missing_later_entrypoint_prevents_all_initializers(self):
        packages = self.copy_packages()
        mod = packages / "observer/innesto-observer.so"
        shutil.copyfile(BUILD / "innesto-test-prior.so", mod)
        status, _, stdout, stderr = self.launch(mods_dir=packages)
        self.assertNotEqual(status, 0)
        self.assertNotIn("host pid=", stdout)
        self.assertNotIn("initialized (pid=", stderr)
        self.assertIn(str(mod), stderr)
        self.assertIn("innesto_mod_init_v1", stderr)

    def test_nonzero_later_initializer_stops_the_remaining_mods_and_host(self):
        packages = self.copy_packages()
        tail = shutil.copytree(packages / "observer", packages / "tail")
        manifest = tail / "innesto.mod.json"
        manifest.write_text(json.dumps({**json.loads(manifest.read_text()),
                                        "id": "tail", "depends": {"observer": "*"}}))
        mod = packages / "observer/innesto-observer.so"
        shutil.copyfile(BUILD / "innesto-test-reject.so", mod)
        status, pid, stdout, stderr = self.launch(mods_dir=packages)
        self.assertNotEqual(status, 0)
        self.assertNotIn("host pid=", stdout)
        self.assertEqual(stderr.count(f"Innesto hello initialized (pid={pid})"), 1)
        self.assertNotIn("Innesto observer initialized", stderr)
        self.assertIn(str(mod), stderr)
        self.assertIn("returned 27", stderr)

    def test_native_handoff_closes_fds_before_mod_code_and_requires_complete_paths(self):
        # The test owns the handoff so it can supply a malformed plan and identify
        # the exact descriptors that must already be closed in the mod constructor.
        mod = self.work / os.fsdecode(b"context \n:\xff.so")
        subprocess.run([CC, "-shared", "-fPIC", "-I", ROOT / "include",
                        ROOT / "tests/launch_context.c", "-o", mod], check=True)
        header = b"Innesto/3\0server\0" + self.profile["sha256"].encode() + b"\0"
        record = header + b"1\0\0"
        payload = record + os.fsencode(mod)
        child = """\
import os, sys
host, loader, plan = sys.argv[1:]
os.environ.update(LD_PRELOAD=f"/proc/self/fd/{loader}", INNESTO_INIT_PID=str(os.getpid()),
                  INNESTO_LOADER_FD=loader, INNESTO_MOD_LIST_FD=plan,
                  INNESTO_MOD_PATH="stale", INNESTO_PREVIOUS_PRELOAD="",
                  TEST_INNESTO_FDS=f"{loader} {plan}")
os.execl(host, host)
"""
        for handoff, valid in [(payload + b"\0", True), (payload, False), (record + b"relative\0", False),
                               (header + b"2\0\0", False), (header + b"1\0", False),
                               (header + b"1\0-typo\0", False), (header + b"3\0", False),
                               (b"Innesto/3\0shared\0", False), (b"Innesto/3\0client\0bad\0", False), (b"Innesto/other\0", False)]:
            with self.subTest(valid=valid, terminated=handoff.endswith(b"\0")):
                with (BUILD / "innesto-bootstrap.so").open("rb") as loader, \
                        tempfile.TemporaryFile(dir=self.work) as plan:
                    plan.write(handoff)
                    plan.seek(0)
                    fds = (loader.fileno(), plan.fileno())
                    result = subprocess.run([sys.executable, "-c", child, self.profile["executable"],
                                             *map(str, fds)], pass_fds=fds, capture_output=True, timeout=5)
                self.assertEqual(result.returncode == 0, valid, result.stderr)
                self.assertEqual(b"host pid=" in result.stdout, valid)
                if not valid:
                    self.assertIn(b"Innesto:", result.stderr)

    def test_independent_mod_initializes_once_in_the_host(self):
        status, pid, stdout, stderr = self.launch("a b", "--example-option")
        self.assertEqual(status, 0, stderr)
        self.assertIn(f"host pid={pid}\n", stdout)
        self.assertIn("argument=a b\nargument=--example-option\n", stdout)
        self.assertIn("preload=\n", stdout)
        self.assertEqual(re.findall(r"Innesto hello initialized \(pid=(\d+)\)", stderr), [str(pid)])

    def test_reexec_preserves_existing_preloads_without_reinitializing(self):
        prior = BUILD / "innesto-test-prior.so"
        # The dynamic linker accepts whitespace as a separator in LD_PRELOAD.
        # Use an fd-based path even when the checkout itself has spaces.
        with prior.open("rb") as library:
            preload = f"/proc/self/fd/{library.fileno()}"
            status, pid, stdout, stderr = self.launch("--reexec", prior=preload, pass_fds=(library.fileno(),))
        self.assertEqual(status, 0, stderr)
        self.assertNotIn("cannot be preloaded", stderr)
        self.assertEqual(stdout.count(f"preload={preload}\n"), 2)
        self.assertIn("argument=child\n", stdout)
        self.assertEqual(stderr.count(f"Innesto hello initialized (pid={pid})"), 1)

    def test_unknown_build_never_starts_the_host(self):
        status, _, stdout, stderr = self.launch(profile={**self.profile, "sha256": "0" * 64})
        self.assertNotEqual(status, 0)
        self.assertNotIn("host pid=", stdout)
        self.assertNotIn("Innesto hello initialized", stderr)
        self.assertIn("unsupported", stderr.lower())

    def test_unrelated_loader_is_rejected_before_start(self):
        status, _, stdout, stderr = self.launch(loader=BUILD / "innesto-test-prior.so")
        self.assertNotEqual(status, 0)
        self.assertNotIn("host pid=", stdout)
        self.assertIn("bootstrap", stderr.lower())

    def test_module_errors_prevent_host_start(self):
        for name in ("innesto-test-prior.so", "innesto-test-reject.so"):
            with self.subTest(module=name):
                status, _, stdout, stderr = self.launch(mod=BUILD / name)
                self.assertNotEqual(status, 0)
                self.assertNotIn("host pid=", stdout)
                self.assertTrue(stderr.strip())

    def test_mod_must_export_its_own_initializer_function(self):
        # One module exports data. The other only links a mod with a real initializer.
        cases = [
            ("data", "int innesto_mod_init_v1;", []),
            ("dependency", "int unrelated;", ["-Wl,--no-as-needed", self.mod]),
        ]
        for name, source, libs in cases:
            with self.subTest(module=name):
                module = self.work / f"{name}.so"
                subprocess.run([CC, "-shared", "-fPIC", "-x", "c", "-", "-x", "none",
                                *libs, "-o", module], input=source, text=True, check=True)
                status, _, stdout, stderr = self.launch(mod=module)
                self.assertGreater(status, 0, stderr)
                self.assertNotIn("host pid=", stdout)
                self.assertNotIn("Innesto hello initialized", stderr)
                self.assertIn("as its own function", stderr)


if __name__ == "__main__":
    unittest.main()
