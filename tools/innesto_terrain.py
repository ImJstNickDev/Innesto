"""Prepare a process-local terrain pack and protect the dedicated world's registry."""
from contextlib import contextmanager, nullcontext
import fcntl
import hashlib
import os
import re
from pathlib import Path
import shutil
import signal
import tempfile

from adapters.a1_2_10 import terrain, terrain_target as routing
from adapters.a1_2_10.terrain_names import stage_display_names
from innesto_registry import REGISTRY, Registry


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


def check_world_path(world, lease):
    if not os.path.samestat(os.fstat(lease), world.stat()):
        raise ValueError("terrain world directory changed while locked")


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


def start(target, executable, digest, environment, mods, profile, arguments, launch, selected_peer=None,
          migrate=False):
    materials = {m.id: m for mod in mods for m in mod.terrain}
    if migrate and (environment != "server" or not materials or len(arguments) != 2
                    or arguments[0] != "--data-dir"):
        raise ValueError("--migrate-terrain requires shared terrain packages and -- --data-dir WORLD on a server")
    if selected_peer is not None and (environment != "client" or not materials):
        raise ValueError("--terrain-peer requires a client with shared terrain packages")
    world = None
    if environment == "server":
        world = routing.world_for_launch(arguments, bool(materials), REGISTRY)
        if not materials and routing.protected(world, REGISTRY):
            raise ValueError("terrain packages missing for this world; restore them before opening it")
    if not materials:
        if "terrainPackSha256" in profile or "terrainBaseCount" in profile:
            raise ValueError("terrain profile requires its shared material packages")
        # A package-free launch racing a first material launch must use the same
        # lease. Keep legacy utility invocations from creating new save paths.
        if world is not None and routing.opens_dedicated_world(arguments):
            world.mkdir(parents=True, exist_ok=True)
            with directory_lock(world) as lease:
                if routing.protected(world, REGISTRY):
                    raise ValueError("terrain packages missing for this world")
                check_world_path(world, lease)
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
    terrain.check_slot_count(base_count, len(materials))
    stock = terrain.original_pack(Path(executable).resolve())
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "innesto/terrain"
    source_assets = Path(executable).resolve().parent / "assets"
    if cache.resolve().is_relative_to(source_assets.resolve()):
        raise ValueError("terrain runtime cache must be outside the game assets")
    if world is not None:
        if cache.resolve().is_relative_to(world):
            raise ValueError("terrain runtime cache must be outside the world")
        if migrate and not world.is_dir():
            raise ValueError("terrain migration requires an existing managed world")
        world.mkdir(mode=0o700, parents=True, exist_ok=True)
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory_lock(world) if world is not None else nullcontext()) as lease:
        if world is None:
            from adapters.a1_2_10.terrain_peer import peer_order, verify_peer
            peer = routing.peer_address(arguments, profile.get("terrainDashboardPort"), selected_peer)
            order = peer_order(*peer, materials, base_count)
        else:
            identity = {"game": "a1.2.10", "platform": "linux-x86_64", "server": digest,
                        "stock": baseline, "baseCount": base_count}
            registry = Registry(lease, identity)
            order = registry.order(materials, migrate=migrate)
        ordered = [materials[mid] for mid in order]
        with tempfile.TemporaryDirectory(dir=cache, prefix="run-") as temporary:
            runtime = Path(temporary)
            if migrate:
                # Only the ephemeral candidate pack and the registry are needed offline.
                legacy = {} if registry.schema == 1 else None
                candidates = terrain.stage_materials(stock, runtime / "pack", ordered, baseline, legacy_receipts=legacy)
                check_world_path(world, lease)
                changed = registry.accept(candidates, migrate=True, legacy_receipts=legacy)
                print("Terrain registry updated." if changed else "Terrain registry already current.")
                return 0
            copy_assets(source_assets, runtime / "assets", stock)
            generated = runtime / "assets" / stock.relative_to(source_assets)
            generated.parent.chmod(generated.parent.stat().st_mode | 0o700)
            candidates = terrain.stage_materials(stock, generated, ordered, baseline)
            if world is None:
                stage_display_names(runtime / "assets", ordered)
            image = runtime / Path(executable).name
            target.seek(0)
            with image.open("xb") as dest:
                shutil.copyfileobj(target, dest)
            image.chmod(0o500)
            with image.open("rb") as staged:
                if hashlib.file_digest(staged, "sha256").hexdigest() != digest:
                    raise ValueError("staged terrain target identity changed")
                if world is None:
                    receipts = {mid: info["receipt"] for mid, info in candidates.items()}
                    verify_peer(*peer, receipts, base_count, initial_order=order)
                    return run_supervised(lambda: launch(staged, str(image), arguments))
                check_world_path(world, lease)
                registry.accept(candidates)
                arguments = routing.bind_world(arguments, world)

                def launch_world():
                    check_world_path(world, lease)
                    launch(staged, str(image), arguments, lease)

                return run_supervised(launch_world)
