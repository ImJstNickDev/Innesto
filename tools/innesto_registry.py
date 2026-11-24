"""Persistent terrain bindings. The caller holds the world's directory lease throughout."""

import hashlib
import json
import os
import re
import stat

from innesto_packages import MOD_ID, unique_keys


REGISTRY = "innesto-terrain-v1.json"  # Older launchers must see the protected world.
BACKUP = REGISTRY + ".backup-"
PENDING = REGISTRY + ".pending-"
DIGEST = re.compile(r"[0-9a-f]{64}")
IDENTITY = {"game", "platform", "server", "stock", "baseCount"}
DEFINITION = {"gameplay", "visualPolicy", "visual", "receipt"}
BINDING = {"id", "slot", "revision"} | DEFINITION


def _digest(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def _material_id(value):
    if not isinstance(value, str):
        return False
    parts = value.split(":")
    return len(parts) == 2 and all(MOD_ID.fullmatch(part) for part in parts)


def _regular(directory, name, flags=os.O_RDONLY):
    fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError("unreadable terrain registry file")
    return fd


def _read(directory, name):
    with os.fdopen(_regular(directory, name), "rb") as stream:
        return stream.read()


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _save(directory, previous, data):
    # The content-addressed pending name lets a retry finish its own partial
    # write after process death, even during the very first world creation.
    pending = PENDING + _hash(data)
    backup = None if previous is None else BACKUP + _hash(previous)
    if previous is not None and _read(directory, REGISTRY) != previous:
        raise ValueError("terrain registry changed during migration")
    try:
        fd = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=directory)
        created = True
    except FileExistsError:
        fd = _regular(directory, pending, os.O_RDWR)
        created = False
    with os.fdopen(fd, "r+b") as staging:
        original = staging.read()
        if os.fstat(fd).st_nlink != 1 or not data.startswith(original):
            raise ValueError("conflicting pending terrain registry; preserve it for inspection")
        backed_up = False
        replaced = False
        try:
            staging.write(data[len(original):])
            staging.flush()
            os.fsync(fd)
            if backup is not None:
                try:
                    os.link(REGISTRY, backup, src_dir_fd=directory, dst_dir_fd=directory,
                            follow_symlinks=False)
                    backed_up = True
                except FileExistsError:
                    pass
                with os.fdopen(_regular(directory, backup), "rb") as snapshot:
                    if snapshot.read() != previous:
                        raise ValueError("conflicting terrain registry backup")
                    os.fsync(snapshot.fileno())
            # Make the exact prior bytes reachable before publishing the new registry.
            os.fsync(directory)
            os.replace(pending, REGISTRY, src_dir_fd=directory, dst_dir_fd=directory)
            replaced = True
            os.fsync(directory)
        except (OSError, ValueError):
            if replaced:
                if not created:
                    os.link(REGISTRY, pending, src_dir_fd=directory, dst_dir_fd=directory)
                if backup is None:
                    os.unlink(REGISTRY, dir_fd=directory)
                else:
                    os.replace(backup, REGISTRY, src_dir_fd=directory, dst_dir_fd=directory)
                    if not backed_up:
                        os.link(REGISTRY, backup, src_dir_fd=directory, dst_dir_fd=directory)
            elif backed_up:
                os.unlink(backup, dir_fd=directory)
            if not created:
                staging.truncate(len(original))
                staging.flush()
                os.fsync(fd)
            elif not replaced:
                os.unlink(pending, dir_fd=directory)
            os.fsync(directory)
            raise


class Registry:
    def __init__(self, directory, identity):
        if (set(identity) != IDENTITY
                or not all(isinstance(identity[key], str) and identity[key] for key in ("game", "platform"))
                or not all(_digest(identity[key]) for key in ("server", "stock"))
                or type(identity["baseCount"]) is not int or identity["baseCount"] < 1):
            raise ValueError("invalid terrain registry target identity")
        self.directory = directory
        self.identity = dict(identity)
        self.schema = None
        self.rows = {}
        self.pending = None
        try:
            self.raw = _read(directory, REGISTRY)
        except FileNotFoundError:
            self.raw = None
            # A long-lived directory descriptor can retain an earlier view on
            # some filesystems. Enumerate a fresh handle relative to the lease.
            view = os.open(".", os.O_RDONLY | os.O_DIRECTORY, dir_fd=directory)
            try:
                entries = os.listdir(view)
            finally:
                os.close(view)
            if len(entries) == 1 and entries[0].startswith(PENDING) and _digest(entries[0][len(PENDING):]):
                self.pending = entries[0]
            elif entries:
                raise ValueError("nonempty world has no terrain registry; restore the complete world")
            return
        try:
            record = json.loads(self.raw, object_pairs_hook=unique_keys)
        except (ValueError, RecursionError):
            raise ValueError("invalid terrain registry JSON") from None
        if (not isinstance(record, dict) or record.keys() != IDENTITY | {"schema", "materials"}
                or type(record["schema"]) is not int or record["schema"] not in (1, 2)):
            raise ValueError("invalid or unsupported terrain registry schema")
        if type(record["baseCount"]) is not int or any(record[key] != identity[key] for key in IDENTITY):
            raise ValueError("terrain registry mismatch: restore the original target and stock pack")
        self.schema = record["schema"]
        materials = record["materials"]
        if not isinstance(materials, list) or not materials:
            raise ValueError("invalid terrain registry material list")
        for slot, row in enumerate(materials, identity["baseCount"]):
            if self.schema == 1:
                if not isinstance(row, list) or len(row) != 2 or not _digest(row[1]):
                    raise ValueError("invalid legacy terrain registry receipt")
                mid = row[0]
                binding = {"receipt": row[1]}
            else:
                if (not isinstance(row, dict) or row.keys() != BINDING
                        or type(row["slot"]) is not int or row["slot"] != slot
                        or type(row["revision"]) is not int or row["revision"] < 1
                        or not all(_digest(row[key]) for key in DEFINITION)):
                    raise ValueError("invalid terrain registry binding")
                mid, binding = row["id"], row
            if not _material_id(mid) or mid in self.rows:
                raise ValueError("invalid or duplicate terrain registry ID")
            self.rows[mid] = binding
        if self.schema == 1 and list(self.rows) != sorted(self.rows):
            raise ValueError("invalid legacy terrain registry order")

    def order(self, material_ids, migrate=False):
        """Check membership and return saved bindings followed by sorted additions."""
        ids = list(material_ids)
        if not ids or not all(_material_id(mid) for mid in ids) or len(set(ids)) != len(ids):
            raise ValueError("invalid or duplicate terrain package IDs")
        if self.schema is None and migrate:
            raise ValueError("migration requires an existing managed terrain world")
        missing = self.rows.keys() - ids
        if missing:
            raise ValueError(f"terrain registry mismatch: missing package material {min(missing)!r}")
        additions = sorted(set(ids) - self.rows.keys())
        if self.schema is not None and additions and not migrate:
            raise ValueError("terrain registry mismatch: adding materials requires offline migration")
        return [*self.rows, *additions]

    def accept(self, candidates, migrate=False, legacy_receipts=None):
        """Validate staged effective definitions. Return True only when a registry was published."""
        ids = self.order(candidates, migrate)
        rows = {}
        for slot, mid in enumerate(ids, self.identity["baseCount"]):
            definition = candidates[mid]
            if (not isinstance(definition, dict) or definition.keys() != DEFINITION
                    or not all(_digest(value) for value in definition.values())):
                raise ValueError("invalid staged terrain definition")
            old = self.rows.get(mid)
            revision = 1
            if old and self.schema == 1 and old["receipt"] != definition["receipt"]:
                # A previous adapter can reproduce its historical receipt from
                # the same staged inputs, exclusively during offline conversion.
                historical = legacy_receipts.get(mid) if migrate and isinstance(legacy_receipts, dict) else None
                if historical != old["receipt"]:
                    raise ValueError(f"terrain registry mismatch: restore the original package for {mid!r} before enrollment")
            if old and self.schema == 2:
                revision = old["revision"]
                changed = old["receipt"] != definition["receipt"]
                if (old["gameplay"] != definition["gameplay"] or old["visualPolicy"] != definition["visualPolicy"]
                        or changed != (old["visual"] != definition["visual"]) or (changed and not migrate)):
                    raise ValueError(f"terrain registry mismatch: incompatible terrain definition for {mid!r}")
                revision += int(changed)
            rows[mid] = {"id": mid, "slot": slot, "revision": revision, **definition}
        if (self.schema == 1 and not migrate) or (self.schema == 2 and self.rows == rows):
            return False
        record = {**self.identity, "schema": 2, "materials": list(rows.values())}
        data = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
        if self.pending is not None and self.pending != PENDING + _hash(data):
            raise ValueError("first terrain launch was interrupted; restore its original packages")
        _save(self.directory, self.raw, data)
        self.raw, self.schema, self.rows, self.pending = data, 2, rows, None
        return True
