"""Original offline world fixtures for complete backup and recovery."""

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from innesto_registry import BACKUP, REGISTRY
from innesto_terrain import directory_lock
import innesto_world_backup as backup


class WorldBackupTest(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "build"
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.world = self.root / "world"
        self.destination = self.root / "before-transfer"
        self.world.mkdir()
        self.lease = self.enterContext(directory_lock(self.world))
        self.inventory = Path("players/local/inventory")
        self.terrain = Path("regions/terrain")
        self.files = {self.inventory: b"\x00saved item stack\xff", self.terrain: b"saved blocks",
                      Path(REGISTRY): b"prior registry\n", Path(".hidden"): b""}
        for name, data in self.files.items():
            path = self.world / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o640)
        self.history = Path(BACKUP + "original")
        os.link(self.world / REGISTRY, self.world / self.history)
        self.files[self.history] = self.files[Path(REGISTRY)]
        (self.world / "empty").mkdir(mode=0o750)

    def save(self, destination=None):
        with backup.locked_world_backup(self.world, self.lease, destination or self.destination):
            pass

    def test_fresh_and_reused_backup_stay_locked_through_registry_commit(self):
        for _ in range(2):
            with backup.locked_world_backup(self.world, self.lease, self.destination):
                with self.assertRaisesRegex(ValueError, "holds this terrain world"), directory_lock(self.destination):
                    self.fail("backup opened while the source transfer was committing")
            with directory_lock(self.destination):
                self.assertTrue(self.destination.is_dir())

    def test_complete_independent_directory_can_restore_after_live_state_changes(self):
        self.save()
        for name in [Path("."), Path("empty"), *self.files]:
            source = (self.world / name).stat()
            copy = (self.destination / name).stat()
            self.assertFalse(os.path.samestat(source, copy))
            self.assertEqual((source.st_mode, source.st_uid, source.st_gid, source.st_mtime_ns),
                             (copy.st_mode, copy.st_uid, copy.st_gid, copy.st_mtime_ns))
        (self.world / self.inventory).write_bytes(b"changed inventory")
        (self.world / self.terrain).unlink()
        (self.world / REGISTRY).write_bytes(b"provider transferred")
        restored = self.root / "restored"
        shutil.copytree(self.destination, restored)
        self.assertEqual({path.relative_to(restored): path.read_bytes()
                          for path in restored.rglob("*") if path.is_file()}, self.files)
        self.assertTrue((restored / "empty").is_dir())

    def test_reuse_rechecks_nested_bytes_and_independence(self):
        self.save()
        inode = self.destination.stat().st_ino
        self.save()
        self.assertEqual(self.destination.stat().st_ino, inode)
        copied = self.destination / self.inventory
        saved = copied.stat()
        copied.write_bytes(b"x" * saved.st_size)
        os.utime(copied, ns=(saved.st_atime_ns, saved.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, "backup"):
            self.save()
        self.assertEqual(copied.read_bytes(), b"x" * saved.st_size)
        copied.unlink()
        os.link(self.world / self.inventory, copied)
        with self.assertRaisesRegex(ValueError, "backup"):
            self.save()
        self.assertEqual((self.world / self.inventory).read_bytes(), self.files[self.inventory])

    def test_reuse_refuses_missing_file_or_changed_world(self):
        self.save()
        (self.destination / self.history).unlink()
        with self.assertRaisesRegex(ValueError, "backup"):
            self.save()
        self.assertFalse((self.destination / self.history).exists())
        other = self.root / "second"
        self.save(other)
        (self.world / self.terrain).write_bytes(b"world played again")
        with self.assertRaisesRegex(ValueError, "backup"):
            self.save(other)
        self.assertEqual((other / self.terrain).read_bytes(), self.files[self.terrain])

    def test_unrelated_existing_destinations_and_overlap_are_untouched(self):
        external = self.root / "external"
        external.mkdir()
        (external / "unrelated").write_bytes(b"leave intact")
        parent_alias = self.root / "alias"
        parent_alias.symlink_to(self.world / "empty", target_is_directory=True)
        link = self.root / "destination-link"
        link.symlink_to(external, target_is_directory=True)
        regular = self.root / "regular"
        regular.touch()
        for dest in (self.world, self.root, self.world / "inside", parent_alias / "inside",
                     link, regular, external, self.world / "empty"):
            with self.subTest(dest=dest), self.assertRaises((OSError, ValueError)):
                self.save(dest)
        self.assertEqual((external / "unrelated").read_bytes(), b"leave intact")
        self.assertTrue(link.is_symlink())
        self.assertFalse((self.world / "inside").exists())
        self.assertFalse((self.world / "empty" / "inside").exists())

    def test_link_and_fifo_in_source_fail_without_partial_publication(self):
        special = self.world / "untrusted"
        for kind in ("file-link", "dir-link", "fifo"):
            with self.subTest(kind=kind):
                if kind == "fifo":
                    os.mkfifo(special)
                else:
                    special.symlink_to(self.root if kind == "dir-link" else self.world / REGISTRY)
                with self.assertRaises((OSError, ValueError)):
                    self.save()
                self.assertEqual(set(self.root.iterdir()), {self.world})
                special.unlink()
        self.save()

    def test_aliased_world_subdirectory_is_rejected_before_staging(self):
        alias = self.root / "alias"
        alias.symlink_to(self.world / "players", target_is_directory=True)
        parent = alias / "local"
        original_resolve = Path.resolve

        # A bind mount, unlike this unprivileged test alias, retains its separate
        # absolute spelling after resolve(). Its opened device and inode agree.
        def resolve(path, *args, **kwargs):
            if path == parent:
                return path
            return original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve), patch.object(backup.tempfile, "TemporaryDirectory") as staging:
            with self.assertRaisesRegex(ValueError, "backup parent"):
                self.save(parent / "snapshot")
            staging.assert_not_called()
        self.assertEqual(set(p.name for p in parent.iterdir()), {"inventory"})

    def test_io_error_and_source_mutation_before_publication(self):
        with patch.object(backup.os, "fsync", side_effect=OSError("simulated I/O failure")):
            with self.assertRaises(OSError):
                self.save()
        self.assertEqual(set(self.root.iterdir()), {self.world})
        sync = os.fsync
        changed = False

        def change_source(fd):
            nonlocal changed
            sync(fd)
            if not changed:
                changed = True
                (self.world / "added-while-copying").write_bytes(b"new bytes")

        with patch.object(backup.os, "fsync", side_effect=change_source):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.save()
        self.assertEqual(set(self.root.iterdir()), {self.world})
        self.save()
        self.assertEqual((self.destination / "added-while-copying").read_bytes(), b"new bytes")

    def test_atomic_publication_never_replaces_a_racing_empty_directory(self):
        original = backup._publish

        def race(*args):
            self.destination.mkdir()
            self.racing_inode = self.destination.stat().st_ino
            original(*args)

        with patch.object(backup, "_publish", side_effect=race), self.assertRaises(FileExistsError):
            self.save()
        self.assertEqual(self.destination.stat().st_ino, self.racing_inode)
        self.assertEqual(list(self.destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
