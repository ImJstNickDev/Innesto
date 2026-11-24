"""Drive the original simulation fixture through the public package launcher."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(sys.argv.pop(1)).resolve()
CC = sys.argv.pop(1)

ALLOWED = "world=0 drops=1 view=0 successes=1 corrections=0"
DENIED = "world=1 drops=0 view=1 successes=0 corrections=1"
FIRST = "4,64,-3"
SECOND = "0,65,-7"


class BlockBreakTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory(dir=BUILD, prefix="block break ")
        cls.addClassCleanup(scratch.cleanup)
        cls.work = Path(scratch.name)
        cls.packages = cls.work / "installed packages"
        cls.host = BUILD / "innesto-test-block-break-host"
        cls.vanilla = BUILD / "innesto-test-block-break-vanilla"
        for name in ("break-audit", "break-guard", "hello"):
            project = cls.work / name
            subprocess.run(["cmake", "-S", ROOT / "examples" / name, "-B", project,
                            f"-DCMAKE_C_COMPILER={CC}", f"-DINNESTO_INCLUDE_DIR={ROOT / 'include'}"],
                           check=True)
            subprocess.run(["cmake", "--build", project], check=True)
            subprocess.run(["cmake", "--install", project, "--prefix", cls.packages], check=True)
        probe = cls.packages / "probe"
        probe.mkdir()
        subprocess.run([CC, "-std=c11", "-shared", "-fPIC", "-I", ROOT / "include",
                        ROOT / "tests/block_break_probe.c", "-o", probe / "probe.so"], check=True)
        (probe / "innesto.mod.json").write_text(json.dumps({
            "schemaVersion": 1, "id": "test_probe", "version": "1.0.0", "game": "a1.2.10",
            "api": 1, "environment": "server", "entrypoint": "probe.so", "depends": {"break_guard": "*"},
        }), encoding="utf-8")

    def launch(self, *packages, host=None):
        scratch = tempfile.TemporaryDirectory(dir=self.work)
        self.addCleanup(scratch.cleanup)
        run_dir = Path(scratch.name)
        mods = run_dir / "mods"
        mods.mkdir()
        for name in packages:
            shutil.copytree(self.packages / name, mods / name)
        executable = host or self.host
        profile = run_dir / "fixture.json"
        profile.write_text(json.dumps({
            "version": "a1.2.10", "platform": "linux-x86_64", "executable": str(executable),
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        }), encoding="utf-8")
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("INNESTO_") and key != "LD_PRELOAD"}
        return subprocess.run([ROOT / "tools/innesto-run", "--profile", profile, "--loader",
                               BUILD / "innesto-bootstrap.so", "--mods-dir", mods],
                              cwd=run_dir, env=env, text=True, capture_output=True, timeout=10)

    def assert_outcome(self, result, second, listeners):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [f"first {ALLOWED}", f"second {second}"])
        self.assertEqual(result.stderr.splitlines(), listeners)

    def test_no_innesto_exports_in_either_simulation_executable(self):
        for executable in (self.vanilla, self.host):
            with self.subTest(executable=executable.name):
                exported = subprocess.check_output(["nm", "-D", "--defined-only", executable], text=True)
                self.assertNotRegex(exported, r"\binnesto_\w+")

    def test_without_loader_or_listeners_both_hosts_commit_once(self):
        for executable in (self.vanilla, self.host):
            with self.subTest(executable=executable.name):
                plain = subprocess.run([executable], capture_output=True, text=True, timeout=5)
                self.assert_outcome(plain, ALLOWED, [])
                self.assert_outcome(self.launch(host=executable), ALLOWED, [])

    def test_vanilla_simulation_loads_startup_only_mods(self):
        result = self.launch("hello", host=self.vanilla)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [f"first {ALLOWED}", f"second {ALLOWED}"])
        self.assertRegex(result.stderr, r"^Innesto hello initialized \(pid=\d+\)\n$")

    def test_one_listener_observes_each_existing_block(self):
        self.assert_outcome(self.launch("break-audit"), ALLOWED, [f"audit {FIRST}", f"audit {SECOND}"])

    def test_independent_mods_veto_before_world_drop_and_success(self):
        self.assert_outcome(self.launch("break-guard", "break-audit"), DENIED,
                            [f"audit {FIRST}", f"guard {FIRST}", f"audit {SECOND}", f"guard {SECOND}"])

    def test_first_veto_skips_later_mods(self):
        self.assert_outcome(self.launch("probe", "break-guard", "break-audit"), DENIED, [
            f"audit {FIRST}", f"guard {FIRST}", f"probe {FIRST}",
            f"audit {SECOND}", f"guard {SECOND}",
        ])

    def assert_unavailable(self, executable):
        result = self.launch("break-audit", host=executable)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("break_audit requires a server with before-block-break support", result.stderr)
        self.assertIn("mod initialization failed", result.stderr)

    def test_required_listener_on_vanilla_simulation_reports_unavailable(self):
        self.assert_unavailable(self.vanilla)

    def test_inactive_bootstrap_leaves_the_adapted_simulation_unchanged(self):
        for launch_pid in (None, "0"):
            with self.subTest(launch_pid=launch_pid):
                env = {k: v for k, v in os.environ.items() if not k.startswith("INNESTO_")}
                if launch_pid is not None:
                    env["INNESTO_INIT_PID"] = launch_pid
                with (BUILD / "innesto-bootstrap.so").open("rb") as loader:
                    env["LD_PRELOAD"] = f"/proc/self/fd/{loader.fileno()}"
                    result = subprocess.run([self.host], env=env, pass_fds=(loader.fileno(),),
                                            capture_output=True, text=True, timeout=10)
                self.assert_outcome(result, ALLOWED, [])

    def test_legacy_host_setter_does_not_advertise_an_adapter(self):
        legacy_host = self.work / "legacy-host"
        source = """\
#include <innesto/block_break.h>
void innesto_host_set_before_block_break_v1(innesto_before_block_break_v1 callback) { (void)callback; }
int main(void) { return 0; }
"""
        subprocess.run([CC, "-std=c11", "-I", ROOT / "include", "-rdynamic", "-x", "c", "-",
                        "-o", legacy_host], input=source, text=True, check=True)
        self.assert_unavailable(legacy_host)


if __name__ == "__main__":
    unittest.main()
