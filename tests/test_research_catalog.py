"""Check private research history and the reviewed, allowlisted distribution format."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/research/catalog.py"


class Catalogue(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.db = self.root / "catalog.sqlite"
        self.bundle = self.root / "snapshot.json"
        evidence = {}
        for path, content in {"code.txt": "original source", "run.txt": "private runtime detail"}.items():
            (self.root / path).write_text(content)
            evidence[path] = hashlib.sha256(content.encode()).hexdigest()
        self.record = {"key": "owned.rule", "semantic": "block.break.permitted", "role": "dedicated",
                       "subsystem": "voxels", "kind": "function", "state": "verified", "confidence": "high",
                       "claim": "Original fixture returns a decision.", "limits": "Only the original fixture.",
                       "entry": "0x1234", "signature": "int(opaque const*)", "signature_state": "verified",
                       "types": ["private object layout"], "binding": {"kind": "rule", "slot": 31},
                       "evidence": [{"path": "code.txt", "method": "source"}, {"path": "run.txt", "method": "runtime"}]}
        self.snapshot = {"format": 1, "revision": 1, "game": "a1.2.10", "platform": "linux-x86_64",
                         "targets": {"dedicated": "a" * 64}, "artifacts": evidence,
                         "records": [self.record], "links": [], "needs": [{"issue": 3, "key": "owned.rule",
                         "requirement": "Validate the decision in a distributed game."}]}

    def run_cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, TOOL, *args], text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertNotIn("Traceback", result.stderr)
        return result.stdout

    def ingest(self, ok=True):
        self.bundle.write_text(json.dumps(self.snapshot))
        return self.run_cli("import", self.db, self.bundle, "--root", self.root, ok=ok).strip()

    def test_archived_evidence_is_searchable_and_can_be_rehashed(self):
        content = self.root / "legacy"
        content.write_bytes(b"log")
        manifest = self.root / "manifest.jsonl"
        manifest.write_text(json.dumps({"kind": "file", "path": "legacy", "size": 3,
                                        "sha256": hashlib.sha256(b"log").hexdigest()}) + "\n")
        self.snapshot["artifacts"][manifest.name] = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.snapshot["archives"] = [manifest.name]
        self.ingest()
        self.assertEqual(json.loads(self.run_cli("files", self.db, "LEG"))[0]["path"], "legacy")
        self.run_cli("verify", self.db, "--root", self.root, "--archived")
        with sqlite3.connect(self.db) as db:
            db.execute("DELETE FROM archive_files")
        self.run_cli("verify", self.db, "--root", self.root, "--archived", ok=False)
        self.snapshot["revision"] = 2
        self.ingest()
        content.write_bytes(b"new")
        self.run_cli("verify", self.db, "--root", self.root, "--archived", ok=False)

    def test_legacy_snapshot_must_meet_current_rules_before_reuse(self):
        self.ingest()
        review = self.root / "review.json"
        for field, invalid in (("role", None), ("signature", "void(void)")):
            with self.subTest(field=field):
                value = self.record[field]
                self.record[field] = invalid
                doc = json.dumps(self.snapshot, sort_keys=True, separators=(",", ":"))
                digest = hashlib.sha256(doc.encode()).hexdigest()
                with sqlite3.connect(self.db) as db:
                    db.execute("UPDATE snapshots SET digest=?,document=?", (digest, doc))
                review.write_text(json.dumps({"format": 1, "revision": 1, "snapshot": digest,
                    "reviewer": "maintainer", "grants": [{"key": "owned.rule", "mode": "binding",
                                                          "basis": "Original fixture"}]}))
                self.run_cli("export", self.db, review, "--root", self.root, ok=False)
                self.ingest(False)
                self.record[field] = value

    def test_binding_kind_requires_its_cooperative_signature(self):
        self.record["signature"] = "void(void)"
        self.ingest(False)

    def test_null_role_and_null_relationship_keys_are_rejected(self):
        self.record["role"] = None
        self.ingest(False)
        self.record["role"] = "dedicated"
        for field in ("source", "target"):
            link = {"source": "owned.rule", "target": "owned.rule", "relation": "requires"}
            link[field] = None
            self.snapshot["links"] = [link]
            self.ingest(False)
        self.snapshot["links"] = []
        self.snapshot["needs"][0]["key"] = None
        self.ingest(False)

    def test_history_search_and_dependencies(self):
        digest = self.ingest()
        self.assertRegex(digest, "^[0-9a-f]{64}$")
        self.assertEqual(self.ingest(), digest)
        self.snapshot["records"][0]["claim"] = "Correction on later evidence"
        self.ingest(False)
        self.snapshot["revision"] = 2
        self.ingest()
        previous = json.loads(self.run_cli("search", self.db, "decision", "--revision", "1"))
        self.assertEqual([s["key"] for s in previous], ["owned.rule"])
        self.assertEqual(json.loads(self.run_cli("search", self.db, "Correction"))[0]["state"], "verified")
        self.assertEqual(json.loads(self.run_cli("needs", self.db, "--issue", "3"))[0]["key"], "owned.rule")

    def test_lifecycle_and_client_observations_are_searchable_by_subsystem(self):
        self.ingest()
        self.snapshot["revision"] = 2
        self.snapshot["targets"]["client"] = "b" * 64
        domains = {"lifecycle": "dedicated", "rendering": "client", "interface": "client", "assets": "client"}
        for subsystem, role in domains.items():
            self.snapshot["records"].append({
                "key": f"owned.{subsystem}", "semantic": f"fixture.{subsystem}", "role": role,
                "subsystem": subsystem, "kind": "behavior", "state": "inferred", "confidence": "medium",
                "claim": "Observed a fixture phase.", "limits": "Fixture only.",
                "evidence": [{"path": "run.txt", "method": "runtime"}],
            })
        self.ingest()
        for subsystem, role in domains.items():
            with self.subTest(subsystem=subsystem):
                args = ("search", self.db, "--role", role, "--subsystem", subsystem)
                self.assertEqual([r["key"] for r in json.loads(self.run_cli(*args))], [f"owned.{subsystem}"])
                self.assertEqual(json.loads(self.run_cli(*args, "--revision", "1")), [])

    def test_rejects_dangling_links_changed_evidence_and_missing_proof(self):
        self.ingest()
        self.snapshot["revision"] = 2
        self.snapshot["links"] = [{"source": "owned.rule", "target": "absent", "relation": "requires"}]
        self.ingest(False)
        self.snapshot["links"] = []
        self.record["evidence"].pop()
        self.ingest(False)
        self.record["evidence"].append({"path": "run.txt", "method": "runtime"})
        (self.root / "run.txt").write_text("different")
        self.ingest(False)
        self.run_cli("verify", self.db, "--root", self.root, ok=False)
        self.assertEqual(sqlite3.connect(self.db).execute("SELECT count(*) FROM snapshots").fetchone(), (1,))

    def test_snapshot_replays_and_edited_projection_is_never_exported(self):
        digest = self.ingest()
        self.assertEqual(json.loads(self.run_cli("snapshot", self.db)), self.snapshot)
        review = self.root / "review.json"
        review.write_text(json.dumps({"format": 1, "revision": 1, "snapshot": digest, "reviewer": "reviewer",
                            "grants": [{"key": "owned.rule", "mode": "binding", "basis": "Original fixture"}]}))
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE records SET semantic='unreviewed',binding='{}'")
        result = json.loads(self.run_cli("export", self.db, review, "--root", self.root))
        self.assertEqual(result["mappings"][0]["binding"]["slot"], 31)
        self.assertEqual(result["mappings"][0]["id"], self.record["semantic"])
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE snapshots SET document='{}'")
        self.run_cli("export", self.db, review, "--root", self.root, ok=False)

    def test_reviewed_mapping_reaches_the_typed_adapter_only_on_the_pinned_fixture(self):
        image = self.root / "host"
        src = ROOT / "tests/mappings"
        subprocess.run(["cc", "-std=c11", "-Werror", "-DFIXTURE_REVISION=1", "-s",
                        "-I", ROOT / "src", src / "reviewed.c", src / "fixture.c", ROOT / "src/native_adapter.c",
                        "-o", image], check=True)
        self.snapshot["targets"]["dedicated"] = hashlib.sha256(image.read_bytes()).hexdigest()
        (self.root / "code.txt").write_bytes((src / "fixture.c").read_bytes())
        (self.root / "run.txt").write_bytes(subprocess.check_output([image]))
        self.snapshot["artifacts"] = {n: hashlib.sha256((self.root / n).read_bytes()).hexdigest()
                                      for n in ("code.txt", "run.txt")}
        self.snapshot["records"].append({**self.record, "key": "owned.project", "semantic": "block.position",
                                         "signature": "position(opaque const*)", "entry": None,
                                         "binding": {"kind": "position", "slot": 17}})
        review = self.root / "review.json"
        review.write_text(json.dumps({"format": 1, "revision": 1, "snapshot": self.ingest(), "reviewer": "maintainer",
                          "grants": [{"key": r["key"], "mode": "binding", "basis": "Original fixture and adapter"}
                                     for r in self.snapshot["records"]]}))
        public = self.root / "export.json"
        public.write_text(self.run_cli("export", self.db, review, "--root", self.root))
        command = ["private-profile", self.db, review, "--root", self.root, "--mappings", public, "--image", image]
        profile = json.loads(self.run_cli(*command, "--role", "dedicated"))
        table = {r["binding"]["kind"]: (r["id"], str(r["binding"]["slot"])) for r in profile["bindings"]}
        result = subprocess.run([image, profile["role"], profile["image"], hashlib.sha256(image.read_bytes()).hexdigest(),
                                 *table["rule"], *table["position"]], check=True, capture_output=True, text=True)
        self.assertIn("reviewed 4 5 6", result.stdout)
        self.assertIn("block present=1", result.stdout)
        self.run_cli(*command, "--role", "solo", ok=False)
        altered = json.loads(public.read_text())
        altered["format"] = True
        altered["mappings"][0]["binding"]["slot"] = float(altered["mappings"][0]["binding"]["slot"])
        public.write_text(json.dumps(altered))
        self.run_cli(*command, "--role", "dedicated", ok=False)
        public.write_text("{}")
        self.run_cli(*command, "--role", "dedicated", ok=False)
        public.write_text(self.run_cli("export", self.db, review, "--root", self.root))
        with image.open("ab") as stream:
            stream.write(b"other build")
        self.run_cli(*command, "--role", "dedicated", ok=False)

    def test_reviewed_export_is_exact_and_excludes_private_fields(self):
        digest = self.ingest()
        grant = {"key": "owned.rule", "mode": "binding", "basis": "Innesto owns the fixture and declaration."}
        reviewed = {"format": 1, "revision": 1, "snapshot": digest, "reviewer": "fixture maintainer",
                    "grants": [grant]}
        path = self.root / "review.json"
        path.write_text(json.dumps(reviewed))
        result = self.run_cli("export", self.db, path, "--root", self.root)
        self.assertEqual(json.loads(result)["mappings"], [{"id": "block.break.permitted", "role": "dedicated",
                                                          "binding": {"kind": "rule", "slot": 31}}])
        for value in ("0x1234", "private", self.snapshot["targets"]["dedicated"], digest, "code.txt", "opaque"):
            self.assertNotIn(value, result)
        reviewed["snapshot"] = "b" * 64
        path.write_text(json.dumps(reviewed))
        self.run_cli("export", self.db, path, "--root", self.root, ok=False)
        self.snapshot["revision"] = 2
        self.record.update(state="inferred", signature_state="inferred", binding=None)
        reviewed.update(revision=2, snapshot=self.ingest())
        grant["mode"] = "semantic"
        path.write_text(json.dumps(reviewed))
        self.run_cli("export", self.db, path, "--root", self.root, ok=False)


if __name__ == "__main__":
    unittest.main()
