"""Prepare a process-local terrain pack and protect the dedicated world's registry."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import tempfile

from adapters.a1_2_10 import terrain, terrain_target as routing
from adapters.a1_2_10.terrain_names import stage_display_names
from innesto_packages import unique_keys


REGISTRY = "innesto-terrain-v1.json"


@contextmanager
def world_registry(world, receipt):
    world.mkdir(parents=True, exist_ok=True)
    with directory_lock(world) as lease:
        path = world / REGISTRY
        if os.path.lexists(path):
            if path.is_symlink() or not path.is_file():
                raise ValueError("unreadable terrain registry")
            try:
                previous = json.loads(path.read_bytes(), object_pairs_hook=unique_keys)
            except (UnicodeError, ValueError):
                raise ValueError("invalid terrain registry") from None
            if json.dumps(previous, sort_keys=True) != json.dumps(receipt, sort_keys=True):
                raise ValueError("terrain registry mismatch: restore the original material packages and build")
        else:
            if any(world.iterdir()):
                raise ValueError("nonempty world has no terrain registry; start a new world or restore its registry")
            with tempfile.NamedTemporaryFile(mode="w", dir=world, delete=False) as out:
                temporary = Path(out.name)
                try:
                    json.dump(receipt, out, sort_keys=True, indent=2)
                    out.write("\n")
                    out.flush()
                    os.fsync(out.fileno())
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
            fd = os.open(world, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        yield lease


@contextmanager
def directory_lock(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if fd < 3:
            moved = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 3)
            os.close(fd)
            fd = moved
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another Innesto launcher holds this terrain world") from None
        yield fd
    finally:
        os.close(fd)


def copy_assets(source, destination, stock):
    # Copy the other shipped resources so executable-relative lookup works without touching the installation.
    def omit_pack(directory, entries):
        return [stock.name] if Path(directory) == stock.parent else []
    if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("terrain requires an unlinked game asset tree")
    shutil.copytree(source, destination, ignore=omit_pack, copy_function=shutil.copyfile)


def run_supervised(action):
    # The parent owns the temporary installation and registry lease through the game's exit.
    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
    try:
        pid = os.fork()
    except BaseException:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        raise
    if pid == 0:
        try:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            action()
        except BaseException as exc:
            os.write(2, f"innesto-run: {exc}\n".encode(errors="replace"))
        os._exit(1)
    handlers = {}
    def forward(signum, frame):
        try:
            os.kill(pid, signum)
        except ProcessLookupError:
            pass
    try:
        for signum in signals:
            handlers[signum] = signal.signal(signum, forward)
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        _, status = os.waitpid(pid, 0)
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
    code = os.waitstatus_to_exitcode(status)
    return code if code >= 0 else 128 - code


def start(target, executable, digest, environment, mods, profile, arguments, launch, selected_peer=None):
    materials = sorted((m for mod in mods for m in mod.terrain), key=lambda m: m.id)
    if selected_peer is not None and (environment != "client" or not materials):
        raise ValueError("--terrain-peer requires a client with shared terrain packages")
    world = None
    if environment == "server":
        world = routing.world_for_launch(arguments, bool(materials), REGISTRY)
        if not materials and os.path.lexists(world / REGISTRY):
            raise ValueError("terrain packages missing for this world; restore them before opening it")
    if not materials:
        if "terrainPackSha256" in profile or "terrainBaseCount" in profile:
            raise ValueError("terrain profile requires its shared material packages")
        # A package-free launch racing a first material launch must use the same
        # lease. Keep legacy utility invocations from creating new save paths.
        if world is not None and routing.opens_dedicated_world(arguments):
            world.mkdir(parents=True, exist_ok=True)
            with directory_lock(world) as lease:
                if os.path.lexists(world / REGISTRY):
                    raise ValueError("terrain packages missing for this world")
                launch(target, executable, arguments, lease)
        else:
            launch(target, executable, arguments)
        return 0
    baseline = profile.get("terrainPackSha256")
    base_count = profile.get("terrainBaseCount")
    if not isinstance(baseline, str) or not re.fullmatch(r"[0-9a-f]{64}", baseline):
        raise ValueError("terrain requires a trusted terrainPackSha256 in the private profile")
    if type(base_count) is not int or base_count <= 0:
        raise ValueError("terrain requires a trusted terrainBaseCount in the private profile")
    stock = terrain.original_pack(Path(executable).resolve())
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "innesto/terrain"
    source_assets = Path(executable).resolve().parent / "assets"
    if cache.resolve().is_relative_to(source_assets.resolve()):
        raise ValueError("terrain runtime cache must be outside the game assets")
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix="run-") as temporary:
        runtime = Path(temporary)
        copy_assets(source_assets, runtime / "assets", stock)
        generated = runtime / "assets" / stock.relative_to(source_assets)
        generated.parent.chmod(generated.parent.stat().st_mode | 0o700)
        textures = terrain.stage_pack(stock, generated, materials, baseline)
        if world is None:
            stage_display_names(runtime / "assets", materials)
        image = runtime / Path(executable).name
        target.seek(0)
        with image.open("xb") as dest:
            shutil.copyfileobj(target, dest)
        image.chmod(0o500)
        with image.open("rb") as staged:
            if hashlib.file_digest(staged, "sha256").hexdigest() != digest:
                raise ValueError("staged terrain target identity changed")
            if world is None:
                from adapters.a1_2_10.terrain_peer import verify_peer
                peer = routing.peer_address(arguments, profile.get("terrainDashboardPort"), selected_peer)
                verify_peer(*peer, textures, base_count)
                return run_supervised(lambda: launch(staged, str(image), arguments))
            arguments = routing.bind_world(arguments, world)
            receipt = {"schema": 1, "game": "a1.2.10", "platform": "linux-x86_64",
                       "server": digest, "stock": baseline, "baseCount": base_count,
                       "materials": [[key, value] for key, value in textures.items()]}
            with world_registry(world, receipt) as lease:
                return run_supervised(lambda: launch(staged, str(image), arguments, lease))
