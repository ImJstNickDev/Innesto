"""Make a directly restorable snapshot before changing a stopped world's registry."""

from contextlib import contextmanager, ExitStack
import ctypes
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import tempfile


@contextmanager
def _open(name, flags, parent=None):
    fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


def _generation(info):
    # ctime includes writes, metadata changes and changes in hard-link count.
    return info.st_dev, info.st_ino, info.st_ctime_ns


def _copy_metadata(fd, original, attributes):
    current = os.fstat(fd)
    if (current.st_uid, current.st_gid) != (original.st_uid, original.st_gid):
        os.fchown(fd, original.st_uid, original.st_gid)
    os.fchmod(fd, stat.S_IMODE(original.st_mode))
    for name in set(os.listxattr(fd)) - attributes.keys():
        os.removexattr(fd, name)
    for name, value in attributes.items():
        os.setxattr(fd, name, value)
    os.utime(fd, ns=(original.st_atime_ns, original.st_mtime_ns))
    os.fsync(fd)


def _file_digest(fd, copied):
    digest = hashlib.sha256()
    with ExitStack() as stack:
        source = stack.enter_context(os.fdopen(fd, "rb", closefd=False))
        if copied is not None:
            target = stack.enter_context(os.fdopen(copied, "wb", closefd=False))
        while data := source.read(1024 * 1024):
            digest.update(data)
            if copied is not None:
                target.write(data)
    return digest.digest()


def _check_backup_parent(lease, parent):
    # A bind mount can give part of the save a second, unrelated absolute path.
    # Check the opened parent before creating even the temporary wrapper there.
    destination = os.fstat(parent)
    seen = set()

    def fail(error):
        raise error

    for _, _, _, directory in os.fwalk(".", dir_fd=lease, onerror=fail):
        current = os.fstat(directory)
        if os.path.samestat(current, destination):
            raise ValueError("terrain world backup parent is inside the source world")
        identity = (current.st_dev, current.st_ino)
        if identity in seen:
            raise ValueError("repeated directory in terrain world backup")
        seen.add(identity)


def _scan(root, *, copy_to=None, verify_backup=False):
    """Read every entry by directory descriptor. Optionally build an independent copy."""
    contents = {}
    generations = {}
    directories = set()

    def visit(fd, copied, path):
        info = os.fstat(fd)
        file_hash = None
        if stat.S_ISDIR(info.st_mode):
            identity = (info.st_dev, info.st_ino)
            if copied is not None:
                # Also guard against a new alias into staging after preflight.
                target = os.fstat(copied)
                directories.add((target.st_dev, target.st_ino))
            if identity in directories:
                raise ValueError("repeated directory in terrain world backup")
            directories.add(identity)
            for name in os.listdir(fd):
                entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
                is_dir = stat.S_ISDIR(entry.st_mode)
                if not is_dir and not stat.S_ISREG(entry.st_mode):
                    raise ValueError("terrain world backup requires regular files and unlinked directories")
                with ExitStack() as stack:
                    flags = os.O_DIRECTORY if is_dir else os.O_RDONLY
                    source = stack.enter_context(_open(name, flags, fd))
                    if not os.path.samestat(entry, os.fstat(source)):
                        raise ValueError("terrain world backup entry changed while opening")
                    child = None
                    if copied is not None:
                        if is_dir:
                            os.mkdir(name, 0o700, dir_fd=copied)
                            flags = os.O_DIRECTORY
                        else:
                            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                        child = stack.enter_context(_open(name, flags, copied))
                    visit(source, child, path + (name,))
        elif stat.S_ISREG(info.st_mode):
            if verify_backup and info.st_nlink != 1:
                raise ValueError("terrain world backup contains a hard-linked file")
            file_hash = _file_digest(fd, copied)
        else:
            raise ValueError("unexpected file type in terrain world backup")
        attributes = {name: os.getxattr(fd, name) for name in os.listxattr(fd)}
        contents[path] = (info.st_mode, info.st_uid, info.st_gid, info.st_mtime_ns, attributes, file_hash)
        generations[path] = _generation(info)
        if generations[path] != _generation(os.fstat(fd)):
            raise ValueError("terrain world backup input changed during verification")
        if copied is not None:
            _copy_metadata(copied, info, attributes)
        if verify_backup:
            os.fsync(fd)

    # Use a fresh directory stream even if the caller previously enumerated the lease.
    with _open(".", os.O_DIRECTORY, root) as view:
        visit(view, copy_to, ())
    return contents, generations


def _verify(source, candidate, initial):
    restored, entries = _scan(candidate, verify_backup=True)
    contents, originals = initial
    if restored != contents:
        raise ValueError("terrain world backup does not exactly match the stopped world")
    original_inodes = {generation[:2] for generation in originals.values()}
    if any(generation[:2] in original_inodes for generation in entries.values()):
        raise ValueError("terrain world backup shares storage entries with the world")
    if _scan(source) != initial:
        raise ValueError("terrain world changed while creating its backup")


def _publish(staging, parent, name):
    # rename(2) can replace an unrelated empty directory created after verification.
    # The supported Linux target provides atomic no-replace for directories.
    renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    if renameat2(staging, b"world", parent, os.fsencode(name), 1) != 0:  # RENAME_NOREPLACE
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), name)


@contextmanager
def locked_world_backup(world: Path, lease: int, destination: Path):
    """Publish or verify a complete backup and hold its lease through the source commit."""
    world = Path(world).resolve(strict=True)
    destination = Path(destination)
    parent_path = destination.parent.resolve(strict=True)
    name = destination.name
    if not name or name == "..":
        raise ValueError("terrain world backup requires a separate directory name")
    target = parent_path / name
    if target.is_relative_to(world) or world.is_relative_to(target):
        raise ValueError("terrain world backup and source directories must be separate")

    with _open(parent_path, os.O_DIRECTORY) as parent:
        def check_paths():
            if (not os.path.samestat(os.fstat(lease), world.stat())
                    or not os.path.samestat(os.fstat(parent), destination.parent.stat())):
                raise ValueError("terrain world or backup parent changed while locked")

        check_paths()
        _check_backup_parent(lease, parent)
        try:
            existing = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if not stat.S_ISDIR(existing.st_mode):
                raise ValueError("terrain world backup destination exists and is not a directory")
            with _open(name, os.O_DIRECTORY, parent) as candidate:
                fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                _verify(lease, candidate, _scan(lease))
                if not os.path.samestat(os.fstat(candidate), os.stat(name, dir_fd=parent, follow_symlinks=False)):
                    raise ValueError("terrain world backup destination changed")
                check_paths()
                os.fsync(parent)
                yield
            return

        # Pin staging to the opened parent, even if an ancestor is renamed. The
        # wrapper stays private while the copy acquires the source's permissions.
        with tempfile.TemporaryDirectory(prefix=".innesto-backup-", dir=f"/proc/self/fd/{parent}") as temp:
            with _open(temp, os.O_DIRECTORY) as staging:
                os.mkdir("world", 0o700, dir_fd=staging)
                with _open("world", os.O_DIRECTORY, staging) as candidate:
                    fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    initial = _scan(lease, copy_to=candidate)
                    _verify(lease, candidate, initial)
                    check_paths()
                    _publish(staging, parent, name)
                    os.fsync(parent)
                    yield
