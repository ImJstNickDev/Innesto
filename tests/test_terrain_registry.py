"""Original fixtures for world registry conversion and interrupted publication."""

import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from innesto_registry import BACKUP, PENDING, REGISTRY, Registry, provider_index


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def material(rgb, family="rock", policy="opaque-static"):
    return {"gameplay": digest(family), "visualPolicy": digest(policy),
            "visual": digest(rgb), "receipt": digest(f"{family}:{policy}:{rgb}")}


def interrupt_publication(world, identity, candidates, boundary):
    lease = os.open(world, os.O_RDONLY | os.O_DIRECTORY)
    sync = os.fsync
    directories = 0

    def interrupt(fd):
        nonlocal directories
        sync(fd)
        if fd == lease:
            directories += 1
            if directories == (1 if boundary == "before" else 2):
                os._exit(73)

    with patch("innesto_registry.os.fsync", side_effect=interrupt):
        Registry(lease, identity).accept(candidates, migrate=True)


class RegistryTest(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "build"
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.world = Path(temporary.name)
        self.lease = os.open(self.world, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.lease)
        self.path = self.world / REGISTRY
        self.identity = {"server": digest("server"), "stock": digest("stock"),
                         "baseCount": 7, "game": "a1.2.10", "platform": "linux-x86_64"}
        self.installed = {"stone:top": material("black"), "wool:red": material("red")}
        self.next = {"early:blue": material("blue"), **self.installed}

    def registry(self):
        return Registry(self.lease, self.identity)

    def legacy(self):
        rows = [[key, item["receipt"]] for key, item in self.installed.items()]
        # Hand formatting exercises the promise to retain the exact original bytes.
        data = (json.dumps({**self.identity, "schema": 1, "materials": rows}, indent=3) + "\n\n").encode()
        self.path.write_bytes(data)
        return data

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.world.iterdir()}

    def test_legacy_restarts_without_writing_and_enrolls_only_matching_receipts(self):
        original = self.legacy()
        self.assertFalse(self.registry().accept(self.installed))
        self.assertEqual(self.snapshot(), {REGISTRY: original})
        for migrate, packages in ((False, self.next), (True, {"wool:red": self.installed["wool:red"]}),
                                  (True, {**self.installed, "stone:top": material("white")})):
            with self.subTest(migrate=migrate, packages=list(packages)):
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    self.registry().accept(packages, migrate)
                self.assertEqual(self.snapshot(), {REGISTRY: original})

        self.assertTrue(self.registry().accept(self.next, migrate=True))
        bak = BACKUP + hashlib.sha256(original).hexdigest()
        saved = self.path.read_bytes()
        rows = json.loads(saved)["materials"]
        self.assertEqual([(r["id"], r["slot"], r["revision"]) for r in rows],
                         [("stone:top", 7, 1), ("wool:red", 8, 1), ("early:blue", 9, 1)])
        self.assertEqual(self.snapshot(), {REGISTRY: saved, bak: original})
        self.assertEqual(self.registry().order(reversed(self.next)), [r["id"] for r in rows])
        self.assertFalse(self.registry().accept(self.next, migrate=True))
        self.assertFalse(self.registry().accept(self.next))
        self.assertEqual(self.snapshot(), {REGISTRY: saved, bak: original})

    def test_historical_receipt_proof_is_specific_to_offline_schema_one_conversion(self):
        historical = self.legacy()
        current = {**self.installed, "stone:top": {**self.installed["stone:top"], "receipt": digest("new encoding")}}
        proof = {"stone:top": self.installed["stone:top"]["receipt"]}
        for migrate, supplied in ((False, proof), (True, None), (True, {"wrong:key": proof["stone:top"]}),
                                  (True, {"stone:top": digest("other asset")})):
            with self.subTest(migrate=migrate, supplied=supplied):
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    self.registry().accept(current, migrate=migrate, legacy_receipts=supplied)
                self.assertEqual(self.snapshot(), {REGISTRY: historical})
        self.assertTrue(self.registry().accept(current, migrate=True, legacy_receipts=proof))
        saved = self.snapshot()
        self.assertFalse(self.registry().accept(current))
        for migrate in (False, True):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                self.registry().accept(self.installed, migrate=migrate, legacy_receipts=proof)
            self.assertEqual(self.snapshot(), saved)

    def test_visual_revision_keeps_slots_and_every_previous_snapshot(self):
        first = self.legacy()
        self.registry().accept(self.next, migrate=True)
        second = self.path.read_bytes()
        changed = {**self.next, "stone:top": material("gray")}
        for definition in (material("gray", family="plant"), material("gray", policy="different alpha"),
                           {**self.installed["stone:top"], "receipt": digest("inconsistent")},
                           {**self.installed["stone:top"], "visual": digest("inconsistent")}):
            with self.subTest(definition=definition):
                with self.assertRaisesRegex(ValueError, "incompatible"):
                    self.registry().accept({**self.next, "stone:top": definition}, migrate=True)
                self.assertEqual(self.path.read_bytes(), second)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.registry().accept(changed)
        self.registry().accept(changed, migrate=True)
        rows = json.loads(self.path.read_bytes())["materials"]
        self.assertEqual([(r["slot"], r["revision"]) for r in rows], [(7, 2), (8, 1), (9, 1)])
        for original in (first, second):
            self.assertEqual((self.world / (BACKUP + hashlib.sha256(original).hexdigest())).read_bytes(), original)
        self.assertFalse(self.registry().accept(changed, migrate=True))
        with self.assertRaisesRegex(ValueError, "missing"):
            self.registry().accept(self.installed, migrate=True)

    def test_missing_registry_never_uses_a_backup_or_adopts_existing_data(self):
        with self.assertRaisesRegex(ValueError, "existing"):
            self.registry().accept(self.installed, migrate=True)
        self.assertFalse(list(self.world.iterdir()))
        original = self.legacy()
        self.path.rename(self.world / (BACKUP + hashlib.sha256(original).hexdigest()))
        with self.assertRaisesRegex(ValueError, "nonempty world"):
            self.registry()
        self.assertFalse(self.path.exists())

    def test_provider_changes_preserve_world_identity_and_preview_is_read_only(self):
        registry = self.registry()
        registry.accept(self.installed)
        before = self.snapshot()
        replacement = {"new:top": ("stone:top",), "wool:red": ()}
        remap = {"stone:top": "new:top"}
        bindings = registry.bind(replacement, remap, migrate=True)
        self.assertEqual(list(bindings.items()), [("stone:top", "new:top"), ("wool:red", "wool:red")])
        plan = registry.plan(self.installed, migrate=True, bindings=bindings)
        self.assertTrue(plan.changed)
        self.assertEqual(plan.provider_changes, (("stone:top", "stone:top", "new:top"),))
        self.assertTrue(any("stone:top" in action and "new:top" in action and "7" in action
                            for action in plan.actions))
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(registry.commit(plan))
        with self.assertRaisesRegex(ValueError, "stale"):
            registry.commit(plan)
        after = self.snapshot()
        saved = json.loads(after[REGISTRY])
        self.assertEqual(saved["schema"], 3)
        rows = saved["materials"]
        for row, original in zip(rows, json.loads(before[REGISTRY])["materials"], strict=True):
            self.assertEqual({k: v for k, v in row.items() if k != "provider"}, original)
        self.assertEqual([row["provider"] for row in rows], ["new:top", "wool:red"])

        for request, migrate in ((None, False), (remap, True)):
            registry = self.registry()
            bindings = registry.bind(replacement, request, migrate=migrate)
            preview = registry.plan(self.installed, migrate=migrate, bindings=bindings)
            self.assertFalse(preview.changed)
            self.assertFalse(preview.provider_changes)
            self.assertFalse(registry.commit(preview))
            self.assertEqual(self.snapshot(), after)
        installed = {mid: () for mid in self.installed}
        for available in (installed, {**replacement, "stone:top": ()},
                          {"new:top": (), "wool:red": ()}):
            with self.subTest(available=available), self.assertRaises(ValueError):
                registry.bind(available)
        back = registry.bind(installed, {"stone:top": "stone:top"}, migrate=True)
        restore = registry.plan(self.installed, migrate=True, bindings=back)
        self.assertEqual(restore.provider_changes, (("stone:top", "new:top", "stone:top"),))
        self.assertTrue(registry.commit(restore))
        self.assertEqual(json.loads(self.path.read_bytes())["schema"], 3)
        self.assertFalse(self.registry().accept(self.installed))

    def test_missing_bindings_list_every_slot_and_recovery(self):
        self.registry().accept(self.installed)
        for available in ({}, {"other:top": ("stone:top",)}):
            with self.subTest(available=available), self.assertRaises(ValueError) as caught:
                self.registry().bind(available)
            message = str(caught.exception)
            for part in ("missing", "stone:top", "slot 7", "wool:red", "slot 8", "restore"):
                self.assertIn(part, message)

    def test_offline_omission_reports_registry_impact_without_guessing_world_counts(self):
        ids = ["demo:a", "demo:b", "demo:c", "demo:d", "demo:e"]
        self.registry().accept({mid: material(mid) for mid in ids})
        before = self.path.read_bytes()
        for missing, expected in (
            ({"demo:a"}, "4 surviving slots would shift. The first is 'demo:b' (slot 8 to 7)"),
            ({"demo:b", "demo:d"}, "2 surviving slots would shift. The first is 'demo:c' (slot 9 to 8)"),
            ({"demo:a", "demo:b", "demo:d"}, "2 surviving slots would shift. The first is 'demo:c' (slot 9 to 7)"),
            ({"demo:d"}, "1 surviving slot would shift. The first is 'demo:e' (slot 11 to 10)"),
            ({"demo:e"}, "0 surviving slots would shift"),
            (set(ids), "0 surviving slots would shift"),
        ):
            with self.subTest(missing=missing), self.assertRaises(ValueError) as refusal:
                self.registry().bind({mid: () for mid in ids if mid not in missing}, migrate=True)
            self.assertIn(expected, str(refusal.exception))
            self.assertIn("Affected voxel and stack counts are unknown", str(refusal.exception))
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(list(self.world.iterdir()), [self.path])

    def test_alias_index_and_stale_or_modified_preview_inputs(self):
        providers = {"next:top": ("stone:top", "ancient:top"), "wool:red": ()}
        self.assertEqual(provider_index(providers), {"next:top": "next:top", "stone:top": "next:top",
                                                    "ancient:top": "next:top", "wool:red": "wool:red"})
        for invalid in ({**providers, "stone:top": ()}, {**providers, "other:top": ("ancient:top",)},
                        {None: ()}, {"bad.id": ()}, {"next:top": None}, {"next:top": ["bad id"]}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                provider_index(invalid)

        registry = self.registry()
        original = {mid: () for mid in self.installed}
        bindings = registry.bind(original)
        with self.assertRaisesRegex(ValueError, "persistent ID"):
            registry.plan(self.next, bindings=bindings)
        stale = registry.plan(self.next)
        self.registry().accept(self.installed)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "changed|stale"):
            registry.commit(stale)
        registry = self.registry()
        bindings = registry.bind(providers, {"stone:top": "next:top"}, migrate=True)
        bindings["stone:top"] = "other:top"
        with self.assertRaisesRegex(ValueError, "unverified"):
            registry.plan(self.installed, migrate=True, bindings=bindings)
        self.assertEqual(self.snapshot(), before)

    def test_remap_requires_offline_enrollment_compatible_provider_and_exact_fingerprints(self):
        original = {"stone:top": (), "wool:red": ()}
        available = {"new:top": ("stone:top",), "wool:red": ()}
        request = {"stone:top": "new:top"}
        self.legacy()
        with self.assertRaisesRegex(ValueError, "enroll"):
            self.registry().bind(available, request, migrate=True)
        self.registry().accept(self.installed, migrate=True)
        before = self.snapshot()
        registry = self.registry()
        bad = [
            (available, request, False),
            (available, None, True),
            ({"new:top": (), "wool:red": ()}, request, True),
            ({**available, **original}, request, True),
            ({**available, "more:blue": ()}, request, True),
            (available, {"absent:id": "new:top"}, True),
            (available, {"stone:top": "absent:id"}, True),
            (available, {"stone:top": "wool:red"}, True),
            ({"new:top": ("stone:top", "wool:red")}, {**request, "wool:red": "new:top"}, True),
            ({**available, "second:top": ("stone:top",)}, request, True),
            ({"new:top": ("stone:top", "stone:top"), "wool:red": ()}, request, True),
            ({"new:top": ("wrong id",), "wool:red": ()}, request, True),
            ({"new:top": "stone:top", "wool:red": ()}, request, True),
            ({"new:top": ("new:top",), "wool:red": ()}, request, True),
        ]
        for installed, remaps, migrate in bad:
            with self.subTest(installed=installed, remaps=remaps, migrate=migrate), self.assertRaises(ValueError):
                registry.bind(installed, remaps, migrate)
        bindings = registry.bind(available, request, migrate=True)
        for field in self.installed["stone:top"]:
            changed = {**self.installed["stone:top"], field: digest("different")}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "incompatible"):
                registry.plan({**self.installed, "stone:top": changed}, migrate=True, bindings=bindings)
        with self.assertRaisesRegex(ValueError, "incompatible"):
            registry.plan({**self.installed, "stone:top": material("new RGB")}, migrate=True, bindings=bindings)
        self.assertEqual(self.snapshot(), before)

    def test_remapped_world_appends_in_sorted_order_and_rejects_invalid_provider_records(self):
        registry = self.registry()
        registry.accept(self.installed)
        remapped = {"new:top": ("stone:top",), "wool:red": ()}
        bindings = registry.bind(remapped, {"stone:top": "new:top"}, migrate=True)
        registry.commit(registry.plan(self.installed, migrate=True, bindings=bindings))
        installed = {**remapped, "z:last": (), "a:first": ()}
        with self.assertRaisesRegex(ValueError, "migration"):
            registry.bind(installed)
        bindings = registry.bind(installed, migrate=True)
        self.assertEqual(list(bindings), ["stone:top", "wool:red", "a:first", "z:last"])
        candidates = {**self.installed, "a:first": material("green"), "z:last": material("orange")}
        candidates["stone:top"] = material("cyan")
        append = registry.plan(candidates, migrate=True, bindings=bindings)
        self.assertFalse(append.provider_changes)
        registry.commit(append)
        record = json.loads(self.path.read_bytes())
        rows = record["materials"]
        self.assertEqual([(r["slot"], r["revision"]) for r in rows], [(7, 2), (8, 1), (9, 1), (10, 1)])
        for malformed in ({**rows[0], "provider": "wool:red"}, {**rows[0], "provider": "not valid"},
                          {k: v for k, v in rows[0].items() if k != "provider"}, {**rows[0], "slot": 6}):
            self.path.write_text(json.dumps({**record, "materials": [malformed, *rows[1:]]}))
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                self.registry()

    def test_invalid_identities_orders_slots_and_unknown_fields_fail_closed(self):
        legacy = json.loads(self.legacy())
        self.registry().accept(self.installed, migrate=True)
        record = json.loads(self.path.read_bytes())
        binding = record["materials"][0]
        cases = [{**legacy, "materials": list(reversed(legacy["materials"]))},
                 {**legacy, "schema": True}, {**legacy, "schema": 3},
                 {**legacy, "materials": [legacy["materials"][0]] * 2},
                 {**record, "server": digest("different")}, {**record, "baseCount": 7.0},
                 {**record, "materials": [{**binding, "slot": 8}]},
                 {**record, "materials": [{**binding, "slot": 7.0}]},
                 {**record, "materials": [{**binding, "revision": True}]},
                 {**record, "materials": [binding, {**binding, "slot": 8}]},
                 {**record, "materials": [{**binding, "futureField": True}]},
                 {**record, "materials": [{**binding, "gameplay": "invalid"}]}]
        for modified in cases:
            with self.subTest(modified=modified):
                self.path.write_text(json.dumps(modified))
                with self.assertRaises(ValueError):
                    self.registry()
        self.path.write_text('{"schema":1,"schema":1}')
        with self.assertRaises(ValueError):
            self.registry()

    def test_failed_publication_preserves_live_world_and_backup_history(self):
        original = self.legacy()
        self.registry().accept(self.installed, migrate=True)
        (self.world / "save").write_text("existing game state")
        prior = self.snapshot()
        real_fsync = os.fsync
        for failure in ("file", "directory-before", "replace", "directory-after"):
            with self.subTest(failure=failure):
                syncs = 0

                def sync(fd):
                    nonlocal syncs
                    if fd == self.lease:
                        syncs += 1
                    if (failure == "file" and fd != self.lease
                            or failure == "directory-before" and syncs == 1
                            or failure == "directory-after" and syncs == 2):
                        raise OSError("sync fault")
                    real_fsync(fd)

                if failure == "replace":
                    fault = patch("innesto_registry.os.replace", side_effect=OSError("replace fault"))
                else:
                    fault = patch("innesto_registry.os.fsync", side_effect=sync)
                with fault, self.assertRaises(OSError):
                    self.registry().accept(self.next, migrate=True)
                self.assertEqual(self.snapshot(), prior)
        self.assertTrue(self.registry().accept(self.next, migrate=True))
        self.assertIn(original, self.snapshot().values())

    def test_interrupted_publication_retries_without_reverting_played_world(self):
        for boundary in ("before", "after"):
            with self.subTest(boundary=boundary):
                for path in self.world.iterdir():
                    path.unlink()
                original = self.legacy()
                child = multiprocessing.get_context("spawn").Process(
                    target=interrupt_publication, args=(self.world, self.identity, self.next, boundary))
                child.start()
                try:
                    child.join(10)
                    self.assertEqual(child.exitcode, 73)
                finally:
                    if child.is_alive():
                        child.kill()
                        child.join()
                    child.close()
                self.assertEqual(self.path.read_bytes() == original, boundary == "before")
                self.assertEqual(self.registry().accept(self.next, migrate=True), boundary == "before")
                self.assertEqual((self.world / (BACKUP + hashlib.sha256(original).hexdigest())).read_bytes(), original)
                self.assertFalse(any(path.name.startswith(PENDING) for path in self.world.iterdir()))
                played = self.world / "save"
                played.write_text("contains the appended slot")
                with self.assertRaisesRegex(ValueError, "missing"):
                    self.registry().accept(self.installed, migrate=True)
                self.assertEqual(played.read_text(), "contains the appended slot")

    def test_first_publication_can_finish_its_own_partial_file_only(self):
        self.registry().accept(self.installed)
        expected = self.path.read_bytes()
        self.path.unlink()
        pending = self.world / (PENDING + hashlib.sha256(expected).hexdigest())
        pending.write_bytes(expected[:29])
        with self.assertRaisesRegex(ValueError, "interrupted"):
            self.registry().accept(self.next)
        self.assertEqual(pending.read_bytes(), expected[:29])
        self.assertTrue(self.registry().accept(self.installed))
        self.assertEqual(self.snapshot(), {REGISTRY: expected})
        self.path.rename(pending)
        pending.write_text("unrelated bytes")
        with self.assertRaisesRegex(ValueError, "conflicting pending"):
            self.registry().accept(self.installed)
        self.assertEqual(self.snapshot(), {pending.name: b"unrelated bytes"})

    def test_malformed_backup_is_never_overwritten(self):
        original = self.legacy()
        backup = self.world / (BACKUP + hashlib.sha256(original).hexdigest())
        backup.write_bytes(b"unrelated")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "conflicting.*backup"):
            self.registry().accept(self.next, migrate=True)
        self.assertEqual(self.snapshot(), before)

    def test_registry_and_pending_files_do_not_follow_links(self):
        self.registry().accept(self.installed)
        data = self.path.read_bytes()
        self.path.unlink()
        with tempfile.TemporaryDirectory(dir=self.world.parent) as directory:
            target = Path(directory) / "original"
            target.write_bytes(data[:29])
            pending = self.world / (PENDING + hashlib.sha256(data).hexdigest())
            pending.symlink_to(target)
            with self.assertRaises(OSError):
                self.registry().accept(self.installed)
            pending.unlink()
            os.link(target, pending)
            with self.assertRaisesRegex(ValueError, "conflicting pending"):
                self.registry().accept(self.installed)
            self.assertEqual(target.read_bytes(), data[:29])
            pending.unlink()
            self.path.symlink_to(target)
            with self.assertRaises(OSError):
                self.registry()


if __name__ == "__main__":
    unittest.main()
