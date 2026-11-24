#!/usr/bin/env python3
"""Versioned private research catalogue. The runtime never opens this database."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

FORMAT = 1
APPLICATION = 0x494E5253
ROLES = {"client", "dedicated", "solo"}
SUBSYSTEMS = {"registries", "crafting", "inventory", "persistence", "voxels", "simulation", "generation", "creative"}
KINDS = {"function", "type", "behavior", "data-contract", "prerequisite", "match"}
COOPERATIVE_SIGNATURES = {"rule": "int(opaque const*)", "position": "position(opaque const*)"}
STATES = {"discovered", "inferred", "verified"}
METHODS = {"static", "runtime", "differential", "source", "comparison", "artifact", "documentation"}
ID = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = (
    "CREATE TABLE snapshots(revision INTEGER PRIMARY KEY, digest TEXT NOT NULL UNIQUE, game TEXT, platform TEXT, document TEXT NOT NULL)",
    "CREATE TABLE targets(revision REFERENCES snapshots, role TEXT, image TEXT, PRIMARY KEY(revision,role))",
    "CREATE TABLE artifacts(revision REFERENCES snapshots, path TEXT, digest TEXT, PRIMARY KEY(revision,path))",
    """CREATE TABLE archive_files(revision INTEGER, manifest TEXT, path TEXT, size INTEGER, digest TEXT,
       PRIMARY KEY(revision,path), FOREIGN KEY(revision,manifest) REFERENCES artifacts)""",
    """CREATE TABLE records(revision INTEGER, key TEXT, semantic TEXT, role TEXT, subsystem TEXT, kind TEXT,
       state TEXT, confidence TEXT, claim TEXT, limits TEXT, entry TEXT, signature TEXT, signature_state TEXT,
       types TEXT, binding TEXT, PRIMARY KEY(revision,key), FOREIGN KEY(revision,role) REFERENCES targets)""",
    "CREATE INDEX inventory ON records(revision,subsystem,role,semantic)",
    """CREATE TABLE evidence(revision INTEGER, key TEXT, path TEXT, method TEXT, PRIMARY KEY(revision,key,path,method),
       FOREIGN KEY(revision,key) REFERENCES records, FOREIGN KEY(revision,path) REFERENCES artifacts)""",
    """CREATE TABLE links(revision INTEGER, source TEXT, target TEXT, relation TEXT, PRIMARY KEY(revision,source,target,relation),
       FOREIGN KEY(revision,source) REFERENCES records, FOREIGN KEY(revision,target) REFERENCES records)""",
    """CREATE TABLE needs(revision INTEGER, issue INTEGER, key TEXT, requirement TEXT, PRIMARY KEY(revision,issue,key),
       FOREIGN KEY(revision,key) REFERENCES records)""",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(obj, required, optional=()):
    require(isinstance(obj, dict) and set(required) <= obj.keys() <= set(required) | set(optional),
            f"expected fields {', '.join(required)} (optional: {', '.join(optional)})")


def string(value):
    return isinstance(value, str) and value.strip() != "" and "\0" not in value


def check_id(value):
    require(isinstance(value, str) and ID.fullmatch(value) and len(value) <= 200, "invalid semantic identifier")


def positive(value):
    return type(value) is int and 0 < value < 2**63


def choice(value, options, label):
    require(isinstance(value, str) and value in options, f"invalid {label}")


def array(value):
    require(isinstance(value, list), "expected an array")
    return value


def read_json(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, "duplicate JSON field")
            obj[key] = value
        return obj
    with path.open(encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=unique)


def encode(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def relative_name(name):
    return (string(name) and name != "." and name == Path(name).as_posix() and not Path(name).is_absolute()
            and ".." not in Path(name).parts)


def verify_file(root, name, digest, size=None):
    require(relative_name(name), "evidence needs a canonical relative path")
    require(isinstance(digest, str) and HASH.fullmatch(digest), "invalid evidence digest")
    path = (root / name).resolve(strict=True)
    require(path.is_relative_to(root) and path.is_file(), "evidence is outside the root or not a regular file")
    with path.open("rb") as stream:
        require(size is None or os.fstat(stream.fileno()).st_size == size, f"changed evidence size: {name}")
        require(hashlib.file_digest(stream, "sha256").hexdigest() == digest, f"changed evidence: {name}")


def verify_files(root, artifacts):
    root = root.resolve(strict=True)
    for name, digest in artifacts:
        verify_file(root, name, digest)


def archive_entries(root, manifest, expected):
    digest = hashlib.sha256()
    with (root / manifest).open("rb") as stream:
        for raw in stream:
            digest.update(raw)
            entry = json.loads(raw)
            require(isinstance(entry, dict) and relative_name(entry.get("path")), "invalid archive entry")
            if entry.get("kind") in ("symlink-text", "special-unread", "excluded-directory", "excluded-sensitive-name", "excluded-active-output"):
                continue
            fields(entry, ("kind", "path", "size", "sha256"))
            require(entry["kind"] == "file" and type(entry["size"]) is int and entry["size"] >= 0
                    and isinstance(entry["sha256"], str) and HASH.fullmatch(entry["sha256"]), "invalid archive file")
            yield entry["path"], entry["size"], entry["sha256"]
    require(digest.hexdigest() == expected, "archive manifest changed during import")


def verify_archives(db, rev, root, snapshot):
    root = root.resolve(strict=True)
    count = 0
    for manifest in snapshot.get("archives", []):
        for path, size, digest in archive_entries(root, manifest, snapshot["artifacts"][manifest]):
            row = db.execute("SELECT manifest,size,digest FROM archive_files WHERE revision=? AND path=?",
                             (rev, path)).fetchone()
            require(row and tuple(row) == (manifest, size, digest), "archive index differs from manifest")
            verify_file(root, path, digest, size)
            count += 1
    require(count == db.execute("SELECT count(*) FROM archive_files WHERE revision=?", (rev,)).fetchone()[0],
            "unexpected archive index entries")


def insert_record(db, rev, r, artifacts, targets):
    fields(r, ("key", "semantic", "role", "subsystem", "kind", "state", "confidence", "claim", "limits", "evidence"),
           ("entry", "signature", "signature_state", "types", "binding"))
    choice(r["role"], targets, "record role for this snapshot")
    check_id(r["key"])
    check_id(r["semantic"])
    choice(r["subsystem"], SUBSYSTEMS, "subsystem")
    choice(r["kind"], KINDS, "record kind")
    choice(r["state"], STATES, "state")
    choice(r["confidence"], {"low", "medium", "high"}, "confidence")
    require(string(r["claim"]) and string(r["limits"]), "state a claim and its limits")
    evidence = array(r["evidence"])
    require(evidence, "every record needs evidence")
    digests, methods = set(), set()
    for item in evidence:
        fields(item, ("path", "method"))
        require(string(item["path"]) and item["path"] in artifacts, "evidence missing from manifest")
        choice(item["method"], METHODS, "evidence method")
        digests.add(artifacts[item["path"]])
        methods.add(item["method"])
    if r["state"] == "verified":
        require(len(digests) >= 2 and len(methods) >= 2, "verification needs independent evidence and methods")
    status = r.get("signature_state", "unknown")
    prototype = r.get("signature")
    choice(status, {"unknown", "inferred", "verified"}, "signature state")
    require((status == "unknown" and prototype is None) or (status != "unknown" and string(prototype)),
            "signature must agree with its evidence status")
    entry = r.get("entry")
    require(entry is None or (r["kind"] == "function" and isinstance(entry, str)
                              and re.fullmatch(r"0x[0-9a-f]+", entry)), "invalid private function entry")
    types = array(r.get("types", []))
    require(all(string(t) for t in types), "invalid type description")
    binding = r.get("binding")
    if binding is not None:
        fields(binding, ("kind", "slot"))
        choice(binding["kind"], COOPERATIVE_SIGNATURES, "cooperative binding kind")
        require(prototype == COOPERATIVE_SIGNATURES[binding["kind"]], "signature differs from cooperative declaration")
        require(r["kind"] == "function" and r["state"] == status == "verified", "binding must have a verified ABI")
        require(type(binding["slot"]) is int and 0 <= binding["slot"] < 2**32, "invalid cooperative slot")
    db.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (rev, *(r[k] for k in ("key", "semantic", "role", "subsystem", "kind", "state", "confidence",
                                       "claim", "limits")), entry, prototype, status, encode(types),
                encode(binding) if binding else None))
    db.executemany("INSERT INTO evidence VALUES(?,?,?,?)",
                   [(rev, r["key"], e["path"], e["method"]) for e in evidence])


def import_snapshot(db, data, root):
    fields(data, ("format", "revision", "game", "platform", "targets", "artifacts", "records", "links", "needs"), ("archives",))
    rev = data["revision"]
    require(type(data["format"]) is int and data["format"] == FORMAT and positive(rev), "unknown format or revision")
    require(data["game"] == "a1.2.10" and data["platform"] == "linux-x86_64", "unsupported game or platform")
    targets, artifacts = data["targets"], data["artifacts"]
    require(isinstance(targets, dict) and targets and targets.keys() <= ROLES, "unknown or missing target roles")
    require(all(isinstance(v, str) and HASH.fullmatch(v) for v in targets.values()), "invalid target identities")
    require(isinstance(artifacts, dict) and artifacts, "missing evidence manifest")
    verify_files(root, artifacts.items())
    document = encode(data)
    digest = hashlib.sha256(document.encode()).hexdigest()
    existing = db.execute("SELECT digest FROM snapshots WHERE revision=?", (rev,)).fetchone()
    if existing:
        require(existing[0] == digest, "revision already exists with different content")
        return digest
    latest = db.execute("SELECT COALESCE(max(revision),0) FROM snapshots").fetchone()[0]
    require(rev == latest + 1, "append the next consecutive revision")
    db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)", (rev, digest, data["game"], data["platform"], document))
    db.executemany("INSERT INTO targets VALUES(?,?,?)", [(rev, k, v) for k, v in targets.items()])
    db.executemany("INSERT INTO artifacts VALUES(?,?,?)", [(rev, k, v) for k, v in artifacts.items()])
    for manifest in array(data.get("archives", [])):
        require(isinstance(manifest, str) and manifest in artifacts, "archive must be a pinned evidence manifest")
        db.executemany("INSERT INTO archive_files VALUES(?,?,?,?,?)",
                       ((rev, manifest, *entry) for entry in archive_entries(root, manifest, artifacts[manifest])))
    require(array(data["records"]), "empty research snapshot")
    for rec in data["records"]:
        insert_record(db, rev, rec, artifacts, targets)
    for link in array(data["links"]):
        fields(link, ("source", "target", "relation"))
        for field in ("source", "target", "relation"):
            check_id(link[field])
        db.execute("INSERT INTO links VALUES(?,?,?,?)", (rev, link["source"], link["target"], link["relation"]))
    for need in array(data["needs"]):
        fields(need, ("issue", "key", "requirement"))
        check_id(need["key"])
        require(positive(need["issue"]) and string(need["requirement"]), "invalid issue prerequisite")
        db.execute("INSERT INTO needs VALUES(?,?,?,?)", (rev, need["issue"], need["key"], need["requirement"]))
    return digest


def original_snapshot(db, revision):
    row = db.execute("SELECT digest,document FROM snapshots WHERE revision=?", (revision,)).fetchone()
    require(row and hashlib.sha256(row["document"].encode()).hexdigest() == row["digest"],
            "missing or altered snapshot document")
    return row["digest"], json.loads(row["document"])


def export(db, review, root):
    fields(review, ("format", "revision", "snapshot", "reviewer", "grants"))
    require(type(review["format"]) is int and review["format"] == FORMAT and positive(review["revision"])
            and string(review["reviewer"]), "invalid review envelope")
    rev = review["revision"]
    require(rev == db.execute("SELECT max(revision) FROM snapshots").fetchone()[0], "review is superseded")
    digest, snap = original_snapshot(db, rev)
    require(digest == review["snapshot"], "review does not match this snapshot")
    verify_files(root, snap["artifacts"].items())
    by_key = {r["key"]: r for r in snap["records"]}
    output = []
    names, slots = set(), set()
    for grant in array(review["grants"]):
        fields(grant, ("key", "mode", "basis"))
        choice(grant["mode"], {"semantic", "binding"}, "export mode")
        require(string(grant["basis"]), "record the distribution basis for each grant")
        row = by_key.get(grant["key"])
        require(row and row["state"] == "verified", "only individually verified records can be exported")
        name = row["role"], row["semantic"]
        require(name not in names, "ambiguous semantic export")
        names.add(name)
        item = {"id": row["semantic"], "role": row["role"]}
        if grant["mode"] == "binding":
            require(row.get("binding") and row.get("signature_state") == "verified", "missing verified typed binding")
            binding = row["binding"]
            slot = row["role"], binding["slot"]
            require(slot not in slots, "ambiguous slot export")
            slots.add(slot)
            item["binding"] = {"kind": binding["kind"], "slot": binding["slot"]}
        output.append(item)
    require(output, "empty review")
    return {"format": 1, "game": snap["game"], "platform": snap["platform"],
            "mappings": sorted(output, key=lambda m: (m["role"], m["id"]))}


def private_profile(db, review, args):
    public = export(db, review, args.root)
    require(encode(public) == encode(read_json(args.mappings)), "mapping document differs from the reviewed export")
    _, snap = original_snapshot(db, review["revision"])
    expected = snap["targets"].get(args.role)
    require(expected, "role not present in this snapshot")
    with args.image.open("rb") as image:
        require(hashlib.file_digest(image, "sha256").hexdigest() == expected, "unverified image for this role")
    bindings = [m for m in public["mappings"] if m["role"] == args.role and "binding" in m]
    require(bindings, "no reviewed typed bindings for this role")
    return {"format": 1, "game": public["game"], "platform": public["platform"], "role": args.role,
            "image": expected, "bindings": bindings}


def records(db, args, rev):
    if args.command == "files":
        return [dict(r) for r in db.execute("""SELECT path,size,digest,manifest FROM archive_files
            WHERE revision=? AND instr(lower(path),lower(?))>0 ORDER BY path LIMIT ?""", (rev, args.text, args.limit))]
    if args.command == "needs":
        return [dict(r) for r in db.execute("""SELECT n.issue,n.key,r.role,r.state,n.requirement FROM needs n
            JOIN records r USING(revision,key) WHERE n.revision=? AND (? IS NULL OR n.issue=?)
            ORDER BY n.issue,n.key""", (rev, args.issue, args.issue))]
    if args.command == "show":
        row = db.execute("SELECT * FROM records WHERE revision=? AND key=?", (rev, args.key)).fetchone()
        require(row, "record not found")
        out = dict(row)
        out["types"] = json.loads(out["types"])
        out["binding"] = json.loads(out["binding"]) if out["binding"] else None
        out["evidence"] = [dict(r) for r in db.execute("""SELECT path,method,digest FROM evidence JOIN artifacts
            USING(revision,path) WHERE revision=? AND key=? ORDER BY path,method""", (rev, args.key))]
        out["links"] = [dict(r) for r in db.execute("""SELECT source,relation,target FROM links WHERE revision=?
            AND (source=? OR target=?) ORDER BY source,relation,target""", (rev, args.key, args.key))]
        return out
    filters, values = ["revision=?"], [rev]
    for key in ("subsystem", "kind", "role", "state"):
        if value := getattr(args, key):
            filters.append(key + "=?")
            values.append(value)
    filters.append("""instr(lower(key||' '||semantic||' '||claim||' '||limits||' '||types||' '||
                      coalesce(signature,'')),lower(?))>0""")
    values.append(args.text)
    return [dict(r) for r in db.execute("""SELECT key,semantic,role,subsystem,kind,state,confidence,claim
        FROM records WHERE """ + " AND ".join(filters) + " ORDER BY subsystem,semantic,role,key", values)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("import", "search", "show", "needs", "verify", "export", "history", "snapshot", "files", "private-profile"):
        p = sub.add_parser(command)
        p.add_argument("db", type=Path)
        if command in ("import", "export", "private-profile"):
            p.add_argument("document", type=Path)
        if command in ("import", "verify", "export", "private-profile"):
            p.add_argument("--root", required=True, type=Path)
        if command == "private-profile":
            p.add_argument("--role", required=True, choices=sorted(ROLES))
            p.add_argument("--image", required=True, type=Path)
            p.add_argument("--mappings", required=True, type=Path)
        if command in ("search", "show", "needs", "verify", "snapshot", "files"):
            p.add_argument("--revision", type=int)
        if command in ("search", "files"):
            p.add_argument("text", nargs="?", default="")
        if command == "files":
            p.add_argument("--limit", type=int, default=50)
        if command == "verify":
            p.add_argument("--archived", action="store_true", help="also rehash every indexed historical regular file")
        if command == "search":
            for key, options in (("role", ROLES), ("kind", KINDS), ("subsystem", SUBSYSTEMS), ("state", STATES)):
                p.add_argument("--" + key, choices=sorted(options))
        if command == "show":
            p.add_argument("key")
        if command == "needs":
            p.add_argument("--issue", type=int)
    args = parser.parse_args()
    writing = args.command == "import"
    os.umask(0o077)
    uri = args.db.resolve().as_uri() + ("?mode=rwc" if writing else "?mode=ro")
    try:
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE" if writing else "BEGIN")
            app = db.execute("PRAGMA application_id").fetchone()[0]
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if writing and app == version == 0 and not db.execute("SELECT 1 FROM sqlite_schema").fetchone():
                for sql in SCHEMA:
                    db.execute(sql)
                db.execute(f"PRAGMA application_id={APPLICATION}")
                db.execute(f"PRAGMA user_version={FORMAT}")
            else:
                require((app, version) == (APPLICATION, FORMAT), "unrecognized catalogue or schema version")
            if writing:
                result = import_snapshot(db, read_json(args.document), args.root)
            elif args.command == "private-profile":
                result = private_profile(db, read_json(args.document), args)
            elif args.command == "export":
                result = export(db, read_json(args.document), args.root)
            elif args.command == "history":
                result = [dict(r) for r in db.execute("SELECT revision,digest,game,platform FROM snapshots ORDER BY revision")]
            else:
                rev = args.revision if args.revision is not None else db.execute("SELECT max(revision) FROM snapshots").fetchone()[0]
                require(db.execute("SELECT 1 FROM snapshots WHERE revision=?", (rev,)).fetchone(), "revision not found")
                if args.command == "snapshot":
                    _, result = original_snapshot(db, rev)
                elif args.command == "verify":
                    _, original = original_snapshot(db, rev)
                    verify_files(args.root, original["artifacts"].items())
                    if args.archived:
                        verify_archives(db, rev, args.root, original)
                    result = {"verified_revision": rev}
                else:
                    result = records(db, args, rev)
            db.commit()
        print(result if writing else json.dumps(result, indent=2, ensure_ascii=False))
    except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
        parser.exit(1, f"catalog: {exc}\n")


if __name__ == "__main__":
    main()
