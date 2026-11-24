"""Verify and stage the a1.2.10 native helper selected by the client's Solo menu."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
import re
import shutil
import stat

from innesto_elf import verify_target_image

LIFETIME = "solo-lifetime"


@contextmanager
def _host_image(client_image):
    # Pin the installed sibling itself. A FIFO must not block validation.
    path = client_image.resolve(strict=True).with_name("owserver")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode) or not os.access(f"/proc/self/fd/{fd}", os.X_OK):
        os.close(fd)
        raise ValueError("Solo host must be a regular executable")
    with os.fdopen(fd, "rb") as stream:
        verify_target_image(stream)
        yield stream


def verify_host(client_image, expected_sha256):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise ValueError("Solo requires a trusted soloHostSha256 in the private client profile")
    with _host_image(client_image) as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected_sha256.lower():
        raise ValueError("unsupported Solo host fingerprint")
    return actual


@contextmanager
def stage_solo_host(runtime, client_image, host_digest, world, lease):
    # The game locates its host next to its own executable and both resolve
    # the catalogue from the same sibling assets tree.
    destination = runtime / "owserver"
    with _host_image(client_image) as source, destination.open("xb+") as staged:
        shutil.copyfileobj(source, staged)
        staged.seek(0)
        if hashlib.file_digest(staged, "sha256").hexdigest() != host_digest:
            raise ValueError("staged Solo host fingerprint changed")
        os.fchmod(staged.fileno(), 0o500)
    if not os.path.samestat(os.stat(world), os.fstat(lease)):
        raise ValueError("Solo world directory changed while locked")
    # Bubblewrap's namespace reaper holds a POSIX read lock on this file and
    # a duplicate of the world lease. The GUI can exit while the native host
    # is still saving. Keep the staged installation until the reaper exits.
    with (runtime / LIFETIME).open("xb+") as lifetime:
        try:
            yield
        finally:
            fcntl.lockf(lifetime, fcntl.LOCK_EX)
