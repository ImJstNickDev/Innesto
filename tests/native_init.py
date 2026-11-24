"""Exercise the public launcher with original native fixtures and an independent mod."""
import hashlib
import json
import os
from pathlib import Path
import re
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
        project = cls.work / "standalone example"
        subprocess.run(["cmake", "-S", ROOT / "examples/hello", "-B", project,
                        f"-DCMAKE_C_COMPILER={CC}", f"-DINNESTO_INCLUDE_DIR={ROOT / 'include'}"],
                       check=True)
        subprocess.run(["cmake", "--build", project], check=True)
        cls.mod = project / "innesto-hello.so"
        host = BUILD / "innesto-test-host"
        cls.profile = {"version": "a1.2.10", "platform": "linux-x86_64",
                       "executable": str(host), "sha256": hashlib.sha256(host.read_bytes()).hexdigest()}

    def launch(self, *args, profile=None, mod=None, loader=None, prior=None, pass_fds=()):
        config = self.work / "fixture.json"
        config.write_text(json.dumps(self.profile if profile is None else profile))
        env = {k: v for k, v in os.environ.items() if not k.startswith("INNESTO_") and k != "LD_PRELOAD"}
        if prior:
            env["LD_PRELOAD"] = str(prior)
        with subprocess.Popen([LAUNCHER, "--profile", config, "--loader", loader or BUILD / "innesto-bootstrap.so",
                               "--mod", mod or self.mod, "--", *args],
                              cwd=self.work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, pass_fds=pass_fds) as proc:
            stdout, stderr = proc.communicate(timeout=10)
            return proc.returncode, proc.pid, stdout, stderr

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
