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
from adapters.a1_2_10.terrain import game_key, stage_materials, stage_pack, stock_fingerprint
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
        for name in ("copperfield", "tidepool", "reedbed", "aster", "kiln"):
            out = cls.base / ("build-" + name)
            subprocess.run(["cmake", "-S", ROOT / "examples" / name, "-B", out,
                            "-DINNESTO_INCLUDE_DIR=" + str(ROOT / "include")], check=True, stdout=subprocess.PIPE)
            subprocess.run(["cmake", "--build", out], check=True, stdout=subprocess.PIPE)
            prefix = cls.base / "v2-packages" if name in ("reedbed", "aster", "kiln") else cls.packages
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

    def test_unavailable_solo_namespace_does_not_enroll_a_fresh_world(self):
        self.settings.update(environment="client", soloHostSha256=self.settings["sha256"])
        shutil.copy2(self.host, self.host.with_name("owserver"))
        cmd = self.command()[:-1] + ["--solo-world", self.world]
        isolated_bin = self.instance / "bin"
        isolated_bin.mkdir()
        (isolated_bin / "python3").symlink_to(sys.executable)
        env = {**os.environ, "PATH": str(isolated_bin), "HOME": str(self.instance),
               "XDG_CACHE_HOME": str(self.instance / "cache")}
        for stage in ("missing", "disabled"):
            if stage == "disabled":
                (isolated_bin / "bwrap").symlink_to(shutil.which("false"))
            with self.subTest(stage=stage):
                result = subprocess.run(cmd, env=env, text=True, capture_output=True)
                self.assert_refused(result)
                self.assertRegex(result.stderr, "bubblewrap|cannot mount")
                self.assertEqual(list(self.world.iterdir()), [])

    def test_solo_rejects_the_wrong_host_role_and_unmanaged_saves(self):
        self.settings.update(environment="client", soloHostSha256=self.settings["sha256"])
        shutil.copy2(self.host, self.host.with_name("owserver"))

        def invoke(*flags):
            cmd = self.command()[:-1] + ["--solo-world", self.world, *flags]
            return subprocess.run(cmd, cwd=self.instance, text=True, capture_output=True,
                                  env={**os.environ, "HOME": str(self.instance),
                                       "XDG_CACHE_HOME": str(self.instance / "cache")})

        self.assert_refused(invoke("--", "--play", "127.0.0.1:1"))
        self.assertFalse(self.world.exists())
        self.world.mkdir()
        (self.world / "player").write_bytes(b"existing inventory")
        refused = invoke("--preview-terrain")
        self.assert_refused(refused)
        self.assertIn("nonempty world", refused.stderr)
        self.assertEqual(list(self.world.iterdir()), [self.world / "player"])
        self.assertEqual((self.world / "player").read_bytes(), b"existing inventory")
        self.settings["environment"] = "server"
        self.assert_refused(invoke())

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
        for changed in ({"family": "rock"}, {"tileMeters": 1}, {"displayNames": {"it": "Giunco"}},
                        {"frames": ["rush.png"]}):
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
                # A server which installed Copperfield second has a different
                # but valid layout. The native client's staged descriptor must match it.
                rows[1]["id"], rows[2]["id"] = rows[2]["id"], rows[1]["id"]
                catalogue.write_text(json.dumps({"materials": rows}))
                reordered = invoke()
                self.assertEqual(reordered.returncode, 0, reordered.stderr)
                keys = [row.split()[0] for row in reordered.stdout.splitlines()[3:]]
                self.assertEqual(keys, ["ow_" + rows[i]["key"] for i in (2, 1)])
                path = self.mods / "copperfield/innesto.mod.json"
                original = path.read_text()
                manifest = json.loads(original)
                manifest["content"]["version"] = 2
                manifest["content"]["terrain"][0]["family"] = "plant"
                path.write_text(json.dumps(manifest))
                self.assert_refused(invoke())
                path.write_text(original)
                remapped = self.instance / "remapped-pack"
                stage_materials(self.stock, remapped, materials, stock, providers={"copperfield:ochre": "kiln:ochre"})
                original_package = self.instance / "original-copperfield"
                (self.mods / "copperfield").rename(original_package)
                shutil.copytree(self.base / "v2-packages/kiln", self.mods / "kiln")
                self.assert_refused(invoke())  # replacement client against the original server
                (served / "pack").unlink()
                (served / "pack").symlink_to(remapped / "blocks", target_is_directory=True)
                matched = invoke()
                self.assertEqual(matched.returncode, 0, matched.stderr)
                self.assertIn("Innesto kiln initialized", matched.stderr)
                (self.mods / "kiln").rename(self.instance / "disabled-kiln")
                original_package.rename(self.mods / "copperfield")
                self.assert_refused(invoke())  # original client against the replacement server
                self.assert_refused(invoke(("--play", "127.0.0.1:24712")))
                catalogue.write_text(json.dumps({"materials": rows[:-1]}))
                self.assert_refused(invoke())
            finally:
                server.shutdown()
                thread.join()

    def test_migration_through_launcher_reopens_with_an_earlier_id_at_the_end(self):
        args = ("--data-dir", str(self.world))
        self.assert_loaded(self.launch(*args))
        path = self.world / "innesto-terrain-v1.json"
        record = json.loads(path.read_bytes())
        bindings = record["materials"]
        # Recreate the byte format emitted by the public schema 1 writer.
        record["schema"] = 1
        record["materials"] = [[b["id"], b["receipt"]] for b in bindings]
        legacy = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()
        path.write_bytes(legacy)
        terrain_save = self.world / "populated-fixture"
        terrain_save.write_bytes(b"existing terrain and inventory")
        self.assert_loaded(self.launch(*args))
        self.assertEqual(path.read_bytes(), legacy)
        shutil.copytree(self.base / "v2-packages/aster", self.mods / "aster")
        self.assert_refused(self.launch(*args))

        def migrate(*game_args):
            cmd = self.command(*game_args)
            cmd.insert(cmd.index("--"), "--migrate-terrain")
            return subprocess.run(cmd, cwd=self.instance, env={**os.environ, "XDG_CACHE_HOME": str(self.instance / "cache")},
                                  capture_output=True, text=True, timeout=20)

        self.assert_refused(migrate(*args, "--help"))
        self.assertEqual(path.read_bytes(), legacy)
        result = migrate(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("initialized", result.stderr)
        self.assertNotIn("started ", result.stdout)
        self.assertEqual(json.loads(path.read_bytes())["materials"][:2], bindings)
        stored = json.loads(path.read_text())["materials"]
        self.assertEqual([(b["id"], b["slot"]) for b in stored],
                         [("copperfield:ochre", 1), ("tidepool:lagoon", 2), ("aster:chalk", 3)])
        self.assertEqual((self.world / (path.name + ".backup-" + hashlib.sha256(legacy).hexdigest())).read_bytes(),
                         legacy)
        reopened = self.launch(*args)
        self.assertEqual(reopened.returncode, 0, reopened.stderr)
        observed = [row.split()[0] for row in reopened.stdout.splitlines()[3:]]
        self.assertEqual(observed, ["ow_" + game_key(b["id"]) for b in stored])
        # The actual visual update is opt-in; a stale client still has a different receipt.
        shutil.copyfile(self.mods / "aster/assets/chalk.png", self.mods / "copperfield/assets/ochre.png")
        self.assert_refused(self.launch(*args))
        self.assertEqual(migrate(*args).returncode, 0)
        updated = json.loads(path.read_text())["materials"]
        self.assertEqual(updated[0]["slot"], bindings[0]["slot"])
        self.assertEqual(updated[0]["revision"], 2)
        self.assertNotEqual(updated[0]["receipt"], bindings[0]["receipt"])
        self.assertEqual(updated[1:], stored[1:])
        self.assertEqual(self.launch(*args).returncode, 0)
        enabled = self.mods / "aster"
        enabled.rename(self.instance / "disabled-aster")
        previous = {p.name: p.read_bytes() for p in self.world.iterdir()}
        self.assert_refused(migrate(*args))
        self.assertEqual({p.name: p.read_bytes() for p in self.world.iterdir()}, previous)
        self.assertEqual(terrain_save.read_bytes(), b"existing terrain and inventory")

    def test_provider_transfer_keeps_slots_and_game_bytes_but_changes_peer_proof(self):
        args = ("--data-dir", str(self.world))
        original = self.launch(*args)
        self.assert_loaded(original)
        registry = self.world / "innesto-terrain-v1.json"
        before = registry.read_bytes()
        save = self.world / "player"
        save.write_bytes(b"saved inventory")
        backup = self.instance / "pre-transfer"
        (self.mods / "copperfield").rename(self.instance / "original")
        def offline(*options):
            cmd = self.command(*args)
            cmd[cmd.index("--"):cmd.index("--")] = options
            return subprocess.run(cmd, cwd=self.instance, capture_output=True, text=True, timeout=20,
                                  env={**os.environ, "XDG_CACHE_HOME": str(self.instance / "cache")})

        for options in (["--preview-terrain"], ["--migrate-terrain", "--backup-world", backup]):
            refused = offline(*options)
            self.assert_refused(refused)
            self.assertIn("1 surviving slot would shift", refused.stderr)
            self.assertIn("'tidepool:lagoon' (slot 2 to 1)", refused.stderr)
            self.assertEqual(registry.read_bytes(), before)
            self.assertEqual(save.read_bytes(), b"saved inventory")
            self.assertFalse(backup.exists())

        shutil.copytree(self.base / "v2-packages/kiln", self.mods / "kiln")
        transfer = ["--remap-terrain", "copperfield:ochre=kiln:ochre"]
        self.assert_refused(self.launch(*args))
        self.assert_refused(offline("--migrate-terrain"))
        self.assert_refused(offline("--migrate-terrain", *transfer))
        preview = offline("--preview-terrain", *transfer)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("slot 1 copperfield:ochre", preview.stdout)
        self.assertIn("kiln:ochre", preview.stdout)
        self.assertNotIn("initialized", preview.stderr)
        self.assertEqual(registry.read_bytes(), before)
        self.assertFalse(backup.exists())
        for unsafe in (self.world / "backup", self.mods / "backup", self.host.parent / "backup"):
            self.assert_refused(offline("--migrate-terrain", *transfer, "--backup-world", unsafe))
            self.assertFalse(unsafe.exists())
        applied = offline("--migrate-terrain", *transfer, "--backup-world", backup)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual((backup / registry.name).read_bytes(), before)
        self.assertEqual((backup / save.name).read_bytes(), save.read_bytes())
        after = self.launch(*args)
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertIn("Innesto kiln initialized", after.stderr)
        first = original.stdout.splitlines()[2:]
        second = after.stdout.splitlines()[2:]
        self.assertEqual(first[::2], second[::2])  # stock and unrelated terrain
        old_key, old_png = first[1].split()
        new_key, new_png = second[1].split()
        self.assertEqual(old_key, new_key)
        self.assertNotEqual(new_png, old_png)
        self.assertEqual(png_scanlines(bytes.fromhex(old_png)), png_scanlines(bytes.fromhex(new_png)))
        committed = registry.read_bytes()
        again = offline("--migrate-terrain", *transfer)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(registry.read_bytes(), committed)

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
            offline = self.command(*args)
            offline.insert(offline.index("--"), "--migrate-terrain")
            result = subprocess.run(offline, cwd=self.instance, env={**env, "INNESTO_TEST_HOLD": ""},
                                    capture_output=True, text=True, timeout=10)
            self.assert_refused(result)
            self.assertIn("holds this terrain world", result.stderr)
            self.assert_refused(self.launch(*args))
            process.kill()
            process.wait(timeout=5)
            self.assert_refused(self.launch(*args))
        finally:
            process.communicate(input="\n", timeout=10)
        self.assert_loaded(self.launch(*args))

    def test_orphaned_migration_files_protect_a_world_without_its_packages(self):
        self.world.mkdir()
        self.mods = self.instance / "empty-mods"
        self.mods.mkdir()
        del self.settings["terrainPackSha256"], self.settings["terrainBaseCount"]
        for suffix in ("backup-", "pending-"):
            marker = self.world / ("innesto-terrain-v1.json." + suffix + "1" * 64)
            marker.write_bytes(b"do not overwrite")
            for args in (("--data-dir", str(self.world)), ("--solo", str(self.world))):
                self.assert_refused(self.launch(*args))
            self.assertEqual(marker.read_bytes(), b"do not overwrite")
            marker.unlink()

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
