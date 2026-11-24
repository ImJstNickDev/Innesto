"""Persistent terrain bindings. The caller holds the world's directory lease throughout."""

from dataclasses import dataclass
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


def _index_providers(available):
    if not isinstance(available, dict) or not all(_material_id(mid) for mid in available):
        raise ValueError("invalid terrain package provider IDs")
    index = {mid: mid for mid in available}
    problems = []
    for provider, aliases in sorted(available.items()):
        if not isinstance(aliases, (tuple, list)) or not all(_material_id(mid) for mid in aliases):
            raise ValueError(f"invalid terrain aliases for provider {provider!r}")
        for mid in aliases:
            if mid in available:
                problems.append(f"terrain alias {mid!r} from {provider!r} shadows an installed provider")
            elif mid in index:
                problems.append(f"duplicate terrain alias {mid!r} claimed by {index[mid]!r} and {provider!r}")
            else:
                index[mid] = provider
    return index, problems


def provider_index(available):
    """Index primary and alternate IDs without permitting ambiguous or shadowed names."""
    index, problems = _index_providers(available)
    if problems:
        raise ValueError("invalid terrain provider declarations: " + "; ".join(problems))
    return index


class _VerifiedBindings(dict):
    """Carry the result of package validation across staging without mutating the registry."""
    def __init__(self, registry, migrate, bindings):
        super().__init__(bindings)
        self.validation = (registry, registry.raw, migrate, tuple(self.items()))


@dataclass(frozen=True)
class RegistryPlan:
    _owner: object
    _previous: bytes | None
    _record: bytes
    changed: bool
    actions: tuple
    provider_changes: tuple

    @property
    def rows(self):
        return {row["id"]: row for row in json.loads(self._record)["materials"]}


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
                or type(record["schema"]) is not int or record["schema"] not in (1, 2, 3)):
            raise ValueError("invalid or unsupported terrain registry schema")
        if type(record["baseCount"]) is not int or any(record[key] != identity[key] for key in IDENTITY):
            raise ValueError("terrain registry mismatch: restore the original target and stock pack")
        self.schema = record["schema"]
        materials = record["materials"]
        if not isinstance(materials, list) or not materials:
            raise ValueError("invalid terrain registry material list")
        providers = set()
        for slot, row in enumerate(materials, identity["baseCount"]):
            if self.schema == 1:
                if not isinstance(row, list) or len(row) != 2 or not _digest(row[1]):
                    raise ValueError("invalid legacy terrain registry receipt")
                mid = row[0]
                binding = {"receipt": row[1]}
            else:
                fields = BINDING | {"provider"} if self.schema == 3 else BINDING
                if (not isinstance(row, dict) or row.keys() != fields
                        or type(row["slot"]) is not int or row["slot"] != slot
                        or type(row["revision"]) is not int or row["revision"] < 1
                        or not all(_digest(row[key]) for key in DEFINITION)):
                    raise ValueError("invalid terrain registry binding")
                mid, binding = row["id"], row
                if self.schema == 3:
                    provider = row["provider"]
                    if not _material_id(provider) or provider in providers:
                        raise ValueError("invalid or duplicate terrain registry provider")
                    providers.add(provider)
            if not _material_id(mid) or mid in self.rows:
                raise ValueError("invalid or duplicate terrain registry ID")
            self.rows[mid] = binding
        if self.schema == 3 and any(row["provider"] != mid and row["provider"] in self.rows
                                    for mid, row in self.rows.items()):
            raise ValueError("terrain registry provider shadows a different persistent ID")
        if self.schema == 1 and list(self.rows) != sorted(self.rows):
            raise ValueError("invalid legacy terrain registry order")

    def order(self, material_ids, migrate=False):
        """Check membership and return saved bindings followed by sorted additions."""
        ids = list(material_ids)
        if not all(_material_id(mid) for mid in ids) or len(set(ids)) != len(ids):
            raise ValueError("invalid or duplicate terrain package IDs")
        return list(self.bind(dict.fromkeys(ids, ()), migrate=migrate))

    def bind(self, available, remaps=None, migrate=False):
        """Resolve installed providers for each saved slot. Only an offline request may transfer one."""
        index, problems = _index_providers(available)
        if remaps is None:
            remaps = {}
        if (not isinstance(remaps, dict)
                or not all(_material_id(mid) and _material_id(provider) for mid, provider in remaps.items())):
            raise ValueError("invalid terrain provider remap")
        if self.schema is None and migrate:
            raise ValueError("migration requires an existing managed terrain world")
        if remaps and not migrate:
            raise ValueError("terrain provider remap requires explicit offline migration")
        if remaps and self.schema == 1:
            raise ValueError("enroll this legacy terrain registry with its original packages before a remap")
        unknown = remaps.keys() - self.rows.keys()
        if unknown:
            problems.append("unknown persistent terrain ID in remap: " + ", ".join(sorted(unknown)))
        if self.rows and not available:
            problems.append("terrain packages missing")
        bindings = {}
        assigned = set()
        for slot, (mid, row) in enumerate(self.rows.items(), self.identity["baseCount"]):
            previous = row.get("provider", mid)
            provider = remaps.get(mid, previous)
            where = f"{mid!r} (slot {slot}, provider {provider!r})"
            if provider not in available:
                problems.append(f"missing package material {where}")
            elif index.get(mid) != provider:
                problems.append(f"missing declared alias for {where}")
            if previous != provider and previous in available:
                problems.append(f"previous provider {previous!r} is still installed for {where}")
            if provider in assigned or (provider != mid and provider in self.rows):
                problems.append(f"provider already bound to another persistent ID: {where}")
            assigned.add(provider)
            bindings[mid] = provider
        additions = sorted(available.keys() - assigned)
        if self.schema is not None and additions:
            listed = ", ".join(additions)
            if remaps:
                problems.append("unexpected package materials during remap: " + listed)
            elif not migrate:
                problems.append("adding materials requires offline migration: " + listed)
        if problems:
            raise ValueError("terrain registry mismatch: " + "; ".join(problems)
                             + ". Restore the required packages or restore a complete matching world backup;"
                               " preview a declared replacement with an explicit offline remap.")
        if not bindings and not additions:
            raise ValueError("no terrain package materials")
        bindings.update((mid, mid) for mid in additions)
        return _VerifiedBindings(self, migrate, bindings)

    def plan(self, candidates, migrate=False, legacy_receipts=None, bindings=None):
        """Check effective definitions keyed by persistent ID without publishing or changing the world."""
        if not isinstance(candidates, dict):
            raise ValueError("invalid staged terrain definitions")
        if bindings is None:
            bindings = self.bind(dict.fromkeys(candidates, ()), migrate=migrate)
        elif (not isinstance(bindings, _VerifiedBindings)
              or bindings.validation != (self, self.raw, migrate, tuple(bindings.items()))):
            raise ValueError("stale or unverified terrain provider bindings")
        if candidates.keys() != bindings.keys():
            raise ValueError("staged terrain definitions must match every persistent ID in the provider bindings")
        changes = tuple((mid, self.rows[mid].get("provider", mid), provider)
                        for mid, provider in bindings.items()
                        if mid in self.rows and self.rows[mid].get("provider", mid) != provider)
        schema = 3 if self.schema == 3 or changes else 2
        actions = []
        rows = {}
        for slot, (mid, provider) in enumerate(bindings.items(), self.identity["baseCount"]):
            definition = candidates[mid]
            if (not isinstance(definition, dict) or definition.keys() != DEFINITION
                    or not all(_digest(value) for value in definition.values())):
                raise ValueError("invalid staged terrain definition")
            old = self.rows.get(mid)
            revision = 1
            action = "keep" if old else "add"
            if old and self.schema == 1 and old["receipt"] != definition["receipt"]:
                # A previous adapter can reproduce its historical receipt from
                # the same staged inputs, exclusively during offline conversion.
                historical = legacy_receipts.get(mid) if migrate and isinstance(legacy_receipts, dict) else None
                if historical != old["receipt"]:
                    raise ValueError(f"terrain registry mismatch: restore the original package for {mid!r} before enrollment")
            if old and self.schema == 1 and migrate:
                action = "enroll"
            if old and self.schema in (2, 3):
                revision = old["revision"]
                previous = old.get("provider", mid)
                if previous != provider:
                    compatible = all(old[key] == definition[key] for key in DEFINITION)
                    action = f"remap provider {previous} -> {provider}"
                else:
                    visual_edit = old["visual"] != definition["visual"]
                    compatible = (old["gameplay"] == definition["gameplay"]
                                  and old["visualPolicy"] == definition["visualPolicy"]
                                  and visual_edit == (old["receipt"] != definition["receipt"])
                                  and (migrate or not visual_edit))
                    if visual_edit:
                        revision += 1
                        action = "update appearance"
                if not compatible:
                    raise ValueError(f"terrain registry mismatch: incompatible terrain definition for {mid!r}")
            rows[mid] = {"id": mid, "slot": slot, "revision": revision, **definition}
            if schema == 3:
                rows[mid]["provider"] = provider
            actions.append(f"slot {slot} {mid}: {action} (provider {provider}, revision {revision})")
        changed = not (self.schema == 1 and not migrate) and self.rows != rows
        record = {**self.identity, "schema": schema, "materials": list(rows.values())}
        data = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
        if self.pending is not None and self.pending != PENDING + _hash(data):
            raise ValueError("first terrain launch was interrupted; restore its original packages")
        return RegistryPlan(self, self.raw, data, changed, tuple(actions), changes)

    def commit(self, plan):
        """Publish a checked plan using the same registry and directory lease used to prepare it."""
        if not isinstance(plan, RegistryPlan) or plan._owner is not self or plan._previous != self.raw:
            raise ValueError("stale terrain registry plan")
        try:
            current = _read(self.directory, REGISTRY)
        except FileNotFoundError:
            current = None
        if current != self.raw:
            raise ValueError("terrain registry changed since preview")
        if not plan.changed:
            return False
        _save(self.directory, self.raw, plan._record)
        self.raw = plan._record
        self.schema = json.loads(self.raw)["schema"]
        self.rows = plan.rows
        self.pending = None
        return True

    def accept(self, candidates, migrate=False, legacy_receipts=None, bindings=None):
        """Validate and publish staged definitions. Return True only when a registry was published."""
        return self.commit(self.plan(candidates, migrate, legacy_receipts, bindings))
