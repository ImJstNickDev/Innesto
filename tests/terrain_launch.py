"""Exercise the public launcher with independent packages and an original asset-reading host."""
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(ROOT / "tools"))
from adapters.a1_2_10.terrain import game_key, stage_pack, stock_fingerprint
from innesto_packages import select_packages


def png_scanlines(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("host did not read a PNG")
    offset = 8
    compressed = bytearray()
    while offset < len(data):
        size, kind = struct.unpack_from(">I4s", data, offset)
        if kind == b"IDAT":
            compressed.extend(data[offset + 8:offset + 8 + size])
        offset += 12 + size
    return zlib.decompress(compressed)


class TerrainLaunch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=BUILD)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.base = Path(cls.tmp.name)
        cls.install = cls.base / "installation"
        cls.install.mkdir()
        code = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    const char *helper = getenv("INNESTO_TEST_HELPER_FD");
    if (helper && argc == 2 && strcmp(argv[1], "--fixture-helper") == 0) {
        int fd = atoi(helper);
        char done;
        close(STDIN_FILENO);
        close(STDOUT_FILENO);
        close(STDERR_FILENO);
        if (setsid() < 0 || write(fd, "R", 1) != 1) return 1;
        return read(fd, &done, 1) < 0;
    }
    if (helper) {
        pid_t pid = fork();
        if (pid < 0) return 1;
        if (pid == 0) {
            execl("/proc/self/exe", argv[0], "--fixture-helper", (char *)NULL);
            _exit(1);
        }
    }
    printf("started %ld\n", (long)getpid());
    fflush(stdout);
    if (getenv("INNESTO_TEST_HOLD") && getchar() == EOF) return 1;
    char path[4096], line[512], key[256], image[300];
    ssize_t size = readlink("/proc/self/exe", path, sizeof(path) - 1);
    if (size < 0) return 1;
    path[size] = 0;
    puts(path);
    char *slash = strrchr(path, '/');
    if (!slash) return 1;
    *slash = 0;
    if (chdir(path) || chdir("assets/textures/packs/default")) return 1;
    FILE *pack = fopen("pack.txt", "r");
    if (!pack) return 1;
    while (fgets(line, sizeof(line), pack)) {
        if (sscanf(line, "tile %255s", key) != 1) continue;
        snprintf(image, sizeof(image), "blocks/%s.png", key);
        FILE *png = fopen(image, "rb");
        if (!png) return 1;
        printf("%s ", key);
        int byte;
        while ((byte = getc(png)) != EOF) printf("%02x", byte);
        putchar('\n');
        if (ferror(png) || fclose(png)) return 1;
    }
    return ferror(pack) || fclose(pack);
}
'''
        subprocess.run(["cc", "-x", "c", "-", "-o", cls.install / "host"], input=code, text=True, check=True)
        cls.pack = cls.install / "assets/textures/packs/default"
        (cls.pack / "blocks").mkdir(parents=True)
        (cls.pack / "pack.txt").write_text("resolution 32\ntile ow_fixture 1.000000 0 roche\n")
        cls.packages = cls.base / "mods"
        for name in ("copperfield", "tidepool", "reedbed"):
            out = cls.base / ("build-" + name)
            subprocess.run(["cmake", "-S", ROOT / "examples" / name, "-B", out,
                            "-DINNESTO_INCLUDE_DIR=" + str(ROOT / "include")], check=True, stdout=subprocess.PIPE)
            subprocess.run(["cmake", "--build", out], check=True, stdout=subprocess.PIPE)
            prefix = cls.base / "v2-packages" if name == "reedbed" else cls.packages
            subprocess.run(["cmake", "--install", out, "--prefix", prefix], check=True, stdout=subprocess.PIPE)
        shutil.copyfile(cls.packages / "copperfield/assets/ochre.png", cls.pack / "blocks/ow_fixture.png")

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=self.base)
        self.addCleanup(temp.cleanup)
        self.instance = Path(temp.name)
        self.mods = self.instance / "mods"
        shutil.copytree(self.packages, self.mods)
        self.world = self.instance / "world"
        self.profile = self.instance / "profile.json"
        install = self.instance / "game"
        shutil.copytree(self.install, install)
        self.host = install / "host"
        self.stock = install / "assets/textures/packs/default"
        self.settings = {"version": "a1.2.10", "platform": "linux-x86_64", "environment": "server",
                         "executable": str(self.host), "sha256": hashlib.sha256(self.host.read_bytes()).hexdigest(),
                         "terrainPackSha256": stock_fingerprint(self.stock), "terrainBaseCount": 1}

    def command(self, *args):
        self.profile.write_text(json.dumps(self.settings))
        return [ROOT / "tools/innesto-run", "--profile", self.profile, "--loader",
                BUILD / "innesto-bootstrap.so", "--mods-dir", self.mods, "--", *args]

    def launch(self, *args):
        return subprocess.run(self.command(*args), cwd=self.instance, capture_output=True, text=True,
                              timeout=25, env={**os.environ, "XDG_CACHE_HOME": str(self.instance / "cache")})

    def assert_loaded(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("copperfield", "tidepool"):
            self.assertEqual(result.stderr.count(f"Innesto {name} initialized"), 1, result.stderr)
        started, exe, *rows = result.stdout.splitlines()
        self.assertRegex(started, r"^started [0-9]+$")
        self.assertNotEqual(exe, str(self.host))
        expected = [("ow_fixture", self.stock / "blocks/ow_fixture.png"),
                    ("ow_innesto_11_copperfield_ochre", self.packages / "copperfield/assets/ochre.png"),
                    ("ow_innesto_8_tidepool_lagoon", self.packages / "tidepool/assets/lagoon.png")]
        self.assertEqual(len(rows), len(expected))
        for row, (name, source) in zip(rows, expected):
            key, image = row.split()
            self.assertEqual(key, name)
            self.assertEqual(png_scanlines(bytes.fromhex(image)), png_scanlines(source.read_bytes()))

    def assert_refused(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout[:128])
        self.assertEqual(result.stdout, "")
        self.assertNotIn("initialized", result.stderr)
        self.assertIn("innesto-run:", result.stderr)

    def test_launch_restart_and_remove(self):
        args = ("--data-dir", str(self.world))
        first = self.launch(*args)
        self.assert_loaded(first)
        lock = self.world / "innesto-terrain-v1.json"
        saved = lock.read_bytes()
        for name, folder in (("tidepool", "aaa"), ("copperfield", "zzz")):
            (self.mods / name).rename(self.mods / folder)
        again = self.launch(*args)
        self.assert_loaded(again)
        self.assertEqual(lock.read_bytes(), saved)
        for folder in self.mods.iterdir():
            shutil.rmtree(folder)
        refused = self.launch(*args)
        self.assert_refused(refused)
        del self.settings["terrainPackSha256"], self.settings["terrainBaseCount"]
        self.assert_refused(self.launch(*args))
        self.assertEqual(lock.read_bytes(), saved)
        self.assertEqual(stock_fingerprint(self.stock), stock_fingerprint(self.pack))

    def test_existing_world_accepts_equivalent_explicit_rock(self):
        args = ("--data-dir", str(self.world))
        self.assert_loaded(self.launch(*args))
        receipt = self.world / "innesto-terrain-v1.json"
        before = receipt.read_bytes()
        path = self.mods / "copperfield/innesto.mod.json"
        manifest = json.loads(path.read_bytes())
        manifest["content"]["version"] = 2
        manifest["content"]["terrain"][0].update(family="rock", tileMeters=1)
        path.write_text(json.dumps(manifest))
        self.assert_loaded(self.launch(*args))
        self.assertEqual(before, receipt.read_bytes())

    def test_independent_plant_package_and_mismatched_gameplay_definition(self):
        shutil.rmtree(self.mods / "tidepool")
        shutil.copytree(self.base / "v2-packages/reedbed", self.mods / "reedbed")
        args = ("--data-dir", str(self.world))
        result = self.launch(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        for mod in ("copperfield", "reedbed"):
            self.assertIn(f"Innesto {mod} initialized", result.stderr)
        receipt = self.world / "innesto-terrain-v1.json"
        before = receipt.read_bytes()
        path = self.mods / "reedbed/innesto.mod.json"
        original = path.read_text()
        for changed in ({"family": "rock"}, {"tileMeters": 1}):
            manifest = json.loads(original)
            manifest["content"]["terrain"][0].update(changed)
            path.write_text(json.dumps(manifest))
            self.assert_refused(self.launch(*args))
            self.assertEqual(receipt.read_bytes(), before)

    def test_visible_client_checks_chosen_peer_before_startup(self):
        served = self.instance / "dashboard"
        (served / "api").mkdir(parents=True)
        materials = [m for package in select_packages(self.mods, "client") for m in package.terrain]
        stock = self.settings["terrainPackSha256"]
        generated = self.instance / "peer-pack"
        stage_pack(self.stock, generated, materials, stock)
        (served / "pack").symlink_to(generated / "blocks", target_is_directory=True)
        rows = [{"id": 0, "key": "fixture"}]
        for index, material in enumerate(materials, 1):
            key = game_key(material.id)
            rows.append({"id": index, "key": key, "texture": f"/pack/ow_{key}.png"})
        catalogue = served / "api/info"
        catalogue.write_text(json.dumps({"materials": rows}))
        with ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=served)) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                self.settings.update(environment="client", terrainDashboardPort=server.server_port)
                args = self.command()
                address = "127.0.0.1:24710"
                args[args.index("--"):args.index("--")] = ["--terrain-peer", address]
                def invoke(extra=()):
                    return subprocess.run([*args, *extra], cwd=self.instance, capture_output=True,
                                          text=True, timeout=10, env={**os.environ, "XDG_CACHE_HOME": str(self.instance / "cache")})
                self.assert_loaded(invoke())
                path = self.mods / "copperfield/innesto.mod.json"
                original = path.read_text()
                manifest = json.loads(original)
                manifest["content"]["version"] = 2
                manifest["content"]["terrain"][0]["family"] = "plant"
                path.write_text(json.dumps(manifest))
                self.assert_refused(invoke())
                path.write_text(original)
                self.assert_refused(invoke(("--play", "127.0.0.1:24712")))
                catalogue.write_text(json.dumps({"materials": rows[:-1]}))
                self.assert_refused(invoke())
            finally:
                server.shutdown()
                thread.join()

    def test_nonempty_world_without_registry(self):
        self.world.mkdir()
        (self.world / "world-data").write_text("previous save")
        result = self.launch("--data-dir", str(self.world))
        self.assert_refused(result)
        self.assertIn("registry", result.stderr)
        self.assertFalse((self.world / "innesto-terrain-v1.json").exists())

    def test_material_launch_requires_pinned_stock_before_opening_a_world(self):
        for field, invalid in (("terrainPackSha256", (None, "invalid", "0" * 64)),
                               ("terrainBaseCount", (True, 0, 1.0))):
            original = self.settings.pop(field)
            cases = [{}] + [{field: value} for value in invalid]
            for index, fields in enumerate(cases):
                with self.subTest(field=field, fields=fields):
                    world = self.instance / f"world-{field}-{index}"
                    self.settings.update(fields)
                    self.assert_refused(self.launch("--data-dir", str(world)))
                    self.assertFalse((world / "innesto-terrain-v1.json").exists())
            self.settings[field] = original
        shutil.copyfile(self.packages / "tidepool/assets/lagoon.png", self.stock / "blocks/ow_fixture.png")
        self.assert_refused(self.launch("--data-dir", str(self.world)))
        self.assertFalse((self.world / "innesto-terrain-v1.json").exists())

    def test_changed_and_missing_packages_preserve_existing_world(self):
        args = ("--data-dir", str(self.world))
        self.assert_loaded(self.launch(*args))
        registry = self.world / "innesto-terrain-v1.json"
        saved = registry.read_bytes()
        ochre = self.mods / "copperfield/assets/ochre.png"
        original = ochre.read_bytes()
        shutil.copyfile(self.mods / "tidepool/assets/lagoon.png", ochre)
        self.assert_refused(self.launch(*args))
        self.assertEqual(registry.read_bytes(), saved)
        ochre.write_bytes(original)
        (self.mods / "tidepool").rename(self.instance / "disabled")
        self.assert_refused(self.launch(*args))
        self.assertEqual(registry.read_bytes(), saved)
        (self.instance / "disabled").rename(self.mods / "tidepool")
        self.assert_loaded(self.launch(*args))

    def test_alternate_server_modes_cannot_open_protected_world(self):
        world = str(self.world)
        self.assert_loaded(self.launch("--data-dir", world))
        registry = self.world / "innesto-terrain-v1.json"
        saved = registry.read_bytes()
        other = str(self.instance / "other")
        cases = (("--solo", world), ("--ghost", world), ("--terrain-worker", world),
                 ("--compact-world", world), ("--verify-world", world, other),
                 ("--verify-world", other, world))
        for installed in (True, False):
            if not installed:
                self.mods.rename(self.instance / "disabled")
                self.mods.mkdir()
                del self.settings["terrainPackSha256"], self.settings["terrainBaseCount"]
                stock = self.launch("--solo", other)
                self.assertEqual(stock.returncode, 0, stock.stderr)
            for args in cases:
                with self.subTest(installed=installed, args=args):
                    self.assert_refused(self.launch(*args))
                    self.assertEqual(registry.read_bytes(), saved)

    def test_registry_in_cwd_does_not_redirect_separate_instance(self):
        previous = self.instance / "owserver_data"
        self.assert_loaded(self.launch("--data-dir", str(previous)))
        registry = previous / "innesto-terrain-v1.json"
        saved = registry.read_bytes()
        remote = self.instance / "another-instance"
        remote.mkdir()
        config = remote / "server.json"
        config.write_text(json.dumps({"dataDir": "owserver_data"}))
        for args in ((str(remote),), ("--config", str(config))):
            with self.subTest(args=args):
                self.assert_refused(self.launch(*args))
                self.assertEqual(registry.read_bytes(), saved)
                self.assertFalse((remote / "owserver_data").exists())

    def test_world_lease_follows_running_game_through_supervisor_exit(self):
        args = ("--data-dir", str(self.world))
        env = {**os.environ, "XDG_CACHE_HOME": str(self.instance / "cache"), "INNESTO_TEST_HOLD": "1"}
        process = subprocess.Popen(self.command(*args), cwd=self.instance, env=env, text=True,
                                   stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "timed out waiting for the game to start")
            started = process.stdout.readline()
            self.assertRegex(started, r"^started [0-9]+\n$")
            self.assertNotEqual(process.pid, int(started.split()[1]))
            self.assert_refused(self.launch(*args))
            process.kill()
            process.wait(timeout=5)
            self.assert_refused(self.launch(*args))
        finally:
            process.communicate(input="\n", timeout=10)
        self.assert_loaded(self.launch(*args))

    def test_default_world_lease_precedes_first_package_free_start(self):
        installed, profile = self.mods, self.settings.copy()
        self.mods = self.instance / "empty-mods"
        self.mods.mkdir()
        del self.settings["terrainPackSha256"], self.settings["terrainBaseCount"]
        world = self.instance / "owserver_data"
        for args in (("--help",), ("--verify-world", "a", "b")):
            with self.subTest(args=args):
                result = self.launch(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(world.exists())
        env = {**os.environ, "XDG_CACHE_HOME": str(self.instance / "cache"), "INNESTO_TEST_HOLD": "1"}
        process = subprocess.Popen(self.command(), cwd=self.instance, env=env, text=True,
                                   stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertTrue(select.select([process.stdout], [], [], 15)[0])
            self.assertRegex(process.stdout.readline(), r"^started [0-9]+\n$")
            self.mods, self.settings = installed, profile
            self.assert_refused(self.launch())
            self.assertTrue(world.is_dir())
            self.assertFalse((world / "innesto-terrain-v1.json").exists())
        finally:
            process.communicate(input="\n", timeout=10)
        self.assert_loaded(self.launch())

    def test_detached_exec_helper_releases_world_as_game_exits(self):
        args = ("--data-dir", str(self.world))
        client, helper = socket.socketpair()
        with client, helper:
            env = {**os.environ, "XDG_CACHE_HOME": str(self.instance / "cache"),
                   "INNESTO_TEST_HELPER_FD": str(helper.fileno())}
            result = subprocess.run(self.command(*args), cwd=self.instance, env=env, text=True,
                                    capture_output=True, timeout=15, pass_fds=(helper.fileno(),))
            self.assert_loaded(result)
            helper.close()
            client.settimeout(5)
            self.assertEqual(client.recv(1), b"R")
            # The helper stays alive on the socket throughout the second launch.
            self.assert_loaded(self.launch(*args))


if __name__ == "__main__":
    unittest.main()
