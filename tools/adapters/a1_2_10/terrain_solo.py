"""The a1.2.10 client's isolated, single-save Survival view on Linux."""
from datetime import datetime, timezone
from functools import cache
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys

from innesto_packages import unique_keys
from innesto_registry import PENDING, REGISTRY
from .solo_host import LIFETIME


SLOT = "innesto-solo"
PENDING_METADATA = ".innesto-solo-metadata.pending"
METADATA = "world.json"
GAME_VERSION = "a1.2.10"
WORLD_FORMAT = {"format": 1, "worldgen_version": 32, "data_format": 1}


def identity_digest(client_digest, helper_digest):
    """Separate native Solo saves from dedicated saves, pinning both game processes."""
    return hashlib.sha256(b"Innesto native solo a1.2.10\0" + bytes.fromhex(client_digest)
                          + bytes.fromhex(helper_digest)).hexdigest()


def _saves_roots(game_dir):
    default = (Path.home() / ".openworld/client").resolve()
    # Older client startup code may consult the default profile before parsing
    # --game-dir. Hide its saves too when the user supplied another profile.
    roots = [game_dir / "saves"]
    if default != game_dir:
        roots.append(default / "saves")
    return roots


def _mount_containment():
    """Compare paths on their underlying filesystems, including bind-mounted subtrees."""
    def unescape(value):
        return Path(os.fsdecode(re.sub(rb"\\([0-7]{3})", lambda m: bytes([int(m[1], 8)]), value)))

    mounts = {}
    for line in Path("/proc/self/mountinfo").read_bytes().splitlines():
        number, _, device, root, point, _ = line.split(b" ", 5)
        mounts[int(number)] = (device, unescape(root), unescape(point))

    @cache
    def position(path):
        # A fresh destination may not exist. Open its nearest existing ancestor
        # to ask the kernel which mount is actually visible, even for stacks.
        ancestor = path
        while True:
            try:
                fd = os.open(ancestor, os.O_PATH | os.O_CLOEXEC)
                break
            except FileNotFoundError:
                if ancestor == ancestor.parent:
                    raise
                ancestor = ancestor.parent
        try:
            with open(f"/proc/self/fdinfo/{fd}", "rb") as info:
                mount_id = next(int(row.split()[1]) for row in info if row.startswith(b"mnt_id:"))
        finally:
            os.close(fd)
        if mount_id not in mounts:
            raise ValueError("mounts changed while checking the native Solo directories")
        device, root, point = mounts[mount_id]
        return device, root / path.relative_to(point)

    @cache
    def subtree_roots(parent):
        # A path under a protected tree can live on a different filesystem,
        # or on a bind mount rooted outside that tree. Include visible child
        # mounts as additional roots without enumerating any saved world data.
        roots = {position(parent)}
        for device, root, point in mounts.values():
            if point.is_relative_to(parent) and position(point.resolve()) == (device, root):
                roots.add((device, root))
        return roots

    def within(path, parent):
        if path.is_relative_to(parent):
            return True
        device, location = position(path)
        return any(device == root_device and location.is_relative_to(root)
                   for root_device, root in subtree_roots(parent))

    return within


def game_directory(world, arguments, *, inputs=()):
    """Resolve the actual profile using only options for the ordinary local menu."""
    valued = {"--game-dir", "--log-dir", "--log-level", "--log-file-level", "--log-profile",
              "--director-window", "--director-size", "--player-name", "--skin-preset"}
    options = {}
    args = iter(arguments)
    for arg in args:
        if arg == "--no-vsync":
            continue
        value = next(args, None)
        if arg not in valued or not value or value.startswith("-") or arg in options:
            raise ValueError("native Solo requires unambiguous options for the ordinary local client menu")
        options[arg] = value
    game_dir = Path(options.get("--game-dir", Path.home() / ".openworld/client")).resolve()
    world = Path(world).resolve()
    sources = [Path(p).resolve() for p in inputs if p is not None]
    within = _mount_containment()
    for source in sources:
        if within(world, source) or within(source, world):
            raise ValueError("keep the managed Solo world separate from the installation, packages and cache")
    logs = Path(options["--log-dir"]).resolve() if "--log-dir" in options else None
    for saves in _saves_roots(game_dir):
        if saves.is_symlink() or (saves.exists() and not saves.is_dir()):
            raise ValueError("native Solo requires an unlinked client saves directory")
        if within(game_dir, saves):
            raise ValueError("keep the native Solo profile outside ordinary client saves")
        if within(world, saves) or within(saves, world):
            raise ValueError("keep the managed Solo world separate from the ordinary client saves")
        if any(within(p, saves) for p in sources):
            raise ValueError("native Solo launcher inputs would be hidden by the saves view")
        if logs and (within(logs, saves) or within(logs, world)):
            raise ValueError("native Solo logs must be outside the world and client saves")
    return game_dir


def _regular(fd):
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise ValueError("invalid Solo save metadata file")


def validate_world(lease, world):
    """Validate native metadata under the same lease as the registered terrain plan."""
    if not os.path.samestat(os.fstat(lease), os.stat(world)):
        raise ValueError("native Solo world directory changed while locked")
    try:
        fd = os.open(METADATA, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=lease)
    except FileNotFoundError:
        view = os.open(".", os.O_DIRECTORY, dir_fd=lease)
        try:
            entries = set(os.listdir(view))
        finally:
            os.close(view)
        if entries - {REGISTRY, PENDING_METADATA} and not (
                len(entries) == 1 and next(iter(entries)).startswith(PENDING)):
            raise ValueError("managed Solo save metadata missing from a populated world")
        return False
    with os.fdopen(fd, "rb") as stream:
        _regular(fd)
        try:
            body = json.load(stream, object_pairs_hook=unique_keys)
        except (ValueError, UnicodeError, RecursionError):
            raise ValueError("invalid Solo save metadata") from None
    if (not isinstance(body, dict) or body.get("last_played_with") != GAME_VERSION
            or any(type(body.get(k)) is not int or body[k] != v for k, v in WORLD_FORMAT.items())
            or body.get("slug") != SLOT or body.get("game_mode") not in ("survival", "creative")
            or not isinstance(body.get("name"), str) or not body["name"]
            or not isinstance(body.get("seed"), str) or not body["seed"]):
        raise ValueError("Solo save metadata does not describe the selected native slot")
    return True


def prepare_world(lease, world):
    """Complete first creation only after the caller accepted and committed the registry."""
    if validate_world(lease, world):
        return
    if not stat.S_ISREG(os.stat(REGISTRY, dir_fd=lease, follow_symlinks=False).st_mode):
        raise ValueError("fresh Solo metadata requires its committed world registry")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {**WORLD_FORMAT, "name": Path(world).name, "slug": SLOT, "seed": str(secrets.randbits(63)),
            "seed_scheme": 2, "terrain": "classic", "game_mode": "survival",
            "created_at": stamp, "last_played_at": stamp, "play_time_s": 0,
            "created_with": GAME_VERSION, "last_played_with": GAME_VERSION,
            "created_worldgen": WORLD_FORMAT["worldgen_version"]}
    fd = os.open(PENDING_METADATA, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                 0o600, dir_fd=lease)
    with os.fdopen(fd, "wb") as staging:
        _regular(fd)
        if os.fstat(fd).st_nlink != 1:
            raise ValueError("invalid pending Solo save metadata")
        os.ftruncate(fd, 0)
        staging.write((json.dumps(body, indent=2) + "\n").encode())
        staging.flush()
        os.fsync(fd)
    # The registered world lease serializes first creation and restart. A
    # hard failure before the rename leaves only the disposable pending file.
    os.replace(PENDING_METADATA, METADATA, src_dir_fd=lease, dst_dir_fd=lease)
    os.fsync(lease)


def _view_command(world, lease, game_dir, runtime, monitor_lease):
    bubblewrap = shutil.which("bwrap")
    if not bubblewrap:
        raise ValueError("native Solo requires bubblewrap with user and network namespaces")
    if not os.path.samestat(os.fstat(lease), os.stat(world)):
        raise ValueError("native Solo world directory changed while locked")
    view = Path(runtime) / "solo-save-view"
    (view / SLOT).mkdir(mode=0o700, parents=True, exist_ok=True)
    cmd = [bubblewrap, "--unshare-user", "--unshare-pid", "--unshare-net",
           "--dev-bind", "/", "/", "--proc", "/proc",
           "--sync-fd", str(monitor_lease), "--lock-file", str(Path(runtime) / LIFETIME)]
    slots = []
    for saves in _saves_roots(game_dir):
        if saves != game_dir / "saves" and not saves.exists():
            continue
        slot = str(saves / SLOT)
        cmd += ["--ro-bind", str(view), str(saves), "--bind", str(world), slot]
        slots.append(slot)
    return cmd, slots


def check_view(world, lease, game_dir, runtime):
    """Prove this save view can be mounted before enrolling a fresh world."""
    cmd, _ = _view_command(world, lease, game_dir, runtime, lease)
    test = subprocess.run([*cmd, "--", sys.executable, "-I", "-S", "-c", "pass"], pass_fds=(lease,),
                          capture_output=True)
    if test.returncode:
        raise ValueError("cannot mount native Solo save view: " + test.stderr.decode(errors="replace").strip())


def exec_in_view(world, lease, game_dir, runtime, target_fd, executable, arguments, env):
    """Enter the isolated client view and exec the previously verified image descriptor."""
    monitor_lease = os.dup(lease)
    os.set_inheritable(monitor_lease, True)
    cmd, slots = _view_command(world, lease, game_dir, runtime, monitor_lease)
    args = list(arguments)
    if "--game-dir" in args:
        args[args.index("--game-dir") + 1] = str(game_dir)
    else:
        args += ["--game-dir", str(game_dir)]

    # bwrap forks and changes PID namespaces. Apply the bootstrap to the game
    # with its actual PID, only once the final namespace is in effect.
    child_env = env.copy()
    child_env["INNESTO_SOLO_PRELOAD"] = child_env.pop("LD_PRELOAD", "")
    trampoline = """import os, sys
count = int(sys.argv[2])
world = os.fstat(int(os.environ['INNESTO_WORLD_LEASE_FD']))
if not all(os.path.samestat(world, os.stat(slot)) for slot in sys.argv[3:3+count]):
    sys.exit("innesto-run: Solo save directory changed before launch")
preload = os.environ.pop('INNESTO_SOLO_PRELOAD')
if preload:
    os.environ['LD_PRELOAD'] = preload
os.environ['INNESTO_INIT_PID'] = str(os.getpid())
image = int(sys.argv[1])
os.set_inheritable(image, False)
os.execve(image, sys.argv[3+count:], os.environ)
"""
    os.set_inheritable(target_fd, True)
    cmd += ["--", sys.executable, "-I", "-S", "-c", trampoline, str(target_fd), str(len(slots)), *slots, executable, *args]
    os.execve(cmd[0], cmd, child_env)
