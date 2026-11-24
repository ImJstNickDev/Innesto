"""Build the three public environment packages once, then launch both projections."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(sys.argv.pop(1)).resolve()
CC = sys.argv.pop(1)


class Environments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory(dir=BUILD, prefix="side tests ")
        cls.addClassCleanup(scratch.cleanup)
        cls.root = Path(scratch.name)
        project = cls.root / "build"
        cls.installed = cls.root / "packages"
        subprocess.run(["cmake", "-S", ROOT / "examples/environments", "-B", project,
                        f"-DCMAKE_C_COMPILER={CC}", f"-DINNESTO_INCLUDE_DIR={ROOT / 'include'}"], check=True)
        subprocess.run(["cmake", "--build", project], check=True)
        subprocess.run(["cmake", "--install", project, "--prefix", cls.installed], check=True)

    def setUp(self):
        scratch = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(scratch.cleanup)
        self.work = Path(scratch.name)
        self.packages = shutil.copytree(self.installed, self.work / "packages")

    def launch(self, environment):
        host = BUILD / "innesto-test-host"
        profile = {"version": "a1.2.10", "platform": "linux-x86_64",
                   "executable": str(host), "sha256": hashlib.sha256(host.read_bytes()).hexdigest()}
        if environment is not None:
            profile["environment"] = environment
        path = self.work / "profile.json"
        path.write_text(json.dumps(profile))
        with subprocess.Popen([ROOT / "tools/innesto-run", "--profile", path, "--loader",
                               BUILD / "innesto-bootstrap.so", "--mods-dir", self.packages],
                              cwd=self.work, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
            stdout, stderr = proc.communicate(timeout=10)
            return proc.returncode, proc.pid, stdout, stderr

    def manifest(self, name, **overrides):
        path = self.packages / name / "innesto.mod.json"
        data = json.loads(path.read_text())
        data.update(overrides)
        path.write_text(json.dumps(data))
        return data

    def test_same_installation_on_both_sides_and_legacy_profile(self):
        for value in ("client", "server", None):
            with self.subTest(environment=value):
                side = value or "server"
                status, pid, stdout, stderr = self.launch(value)
                self.assertEqual(status, 0, stderr)
                self.assertIn(f"host pid={pid}", stdout)
                self.assertEqual(stderr.splitlines(), [
                    f"Innesto {name} {phase} physical={side} logical=unknown pid={pid}"
                    for phase in ("init", "startup-complete") for name in ("shared-hello", f"{side}-hello")])

    def test_inactive_library_is_not_required_and_inactive_dependencies_are_ignored(self):
        data = self.manifest("server-hello", depends={"absent": "*"})
        (self.packages / "server-hello" / data["entrypoint"]).unlink()
        status, _, stdout, stderr = self.launch("client")
        self.assertEqual(status, 0, stderr)
        self.assertIn("host pid=", stdout)
        self.assertNotIn("server-hello", stderr)

    def test_active_dependency_on_filtered_package_fails_before_host(self):
        self.manifest("shared-hello", depends={"server-hello": "*"})
        status, _, stdout, stderr = self.launch("client")
        self.assertNotEqual(status, 0)
        self.assertIn("server-hello", stderr)
        self.assertIn("shared-hello", stderr)
        self.assertIn("client", stderr)
        self.assertNotIn("host pid=", stdout)
        self.assertNotIn("logical=unknown", stderr)

    def test_v1_and_v2_mods_initialize_together(self):
        data = self.manifest("server-hello", api=1)
        library = self.packages / "server-hello" / data["entrypoint"]
        subprocess.run([CC, "-shared", "-fPIC", "-I", ROOT / "include",
                        ROOT / "examples/observer/observer.c", "-o", library], check=True)
        status, pid, stdout, stderr = self.launch("server")
        self.assertEqual(status, 0, stderr)
        self.assertIn("host pid=", stdout)
        self.assertEqual(stderr.splitlines(), [
            f"Innesto shared-hello init physical=server logical=unknown pid={pid}",
            f"Innesto observer initialized (pid={pid})",
            f"Innesto shared-hello startup-complete physical=server logical=unknown pid={pid}",
        ])

    def test_failed_initializer_suppresses_all_startup_complete_callbacks(self):
        data = self.manifest("client-hello")
        library = self.packages / "client-hello" / data["entrypoint"]
        subprocess.run([CC, "-shared", "-fPIC", "-I", ROOT / "include", "-x", "c", "-", "-o", library],
                       input='#include <innesto/runtime.h>\n'
                             'int innesto_mod_init_v2(const struct innesto_mod_context *ctx) { return 17; }',
                       text=True, check=True)
        status, _, stdout, stderr = self.launch("client")
        self.assertNotEqual(status, 0)
        self.assertIn("shared-hello init", stderr)
        self.assertIn("returned 17", stderr)
        self.assertNotIn("startup-complete", stderr)
        self.assertNotIn("host pid=", stdout)

    def test_unknown_profile_environment_is_refused(self):
        for environment in ("integrated", "shared", "", True):
            with self.subTest(environment=environment):
                status, _, stdout, stderr = self.launch(environment)
                self.assertNotEqual(status, 0)
                self.assertIn("environment", stderr)
                self.assertNotIn("host pid=", stdout)

    def test_mismatched_entrypoint_abi_resolves_before_first_initializer(self):
        self.manifest("client-hello", api=1)
        status, _, stdout, stderr = self.launch("client")
        self.assertNotEqual(status, 0)
        self.assertIn("innesto_mod_init_v1", stderr)
        self.assertNotIn("logical=unknown", stderr)
        self.assertNotIn("host pid=", stdout)


if __name__ == "__main__":
    unittest.main()
