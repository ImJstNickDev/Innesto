"""Prepare a process-local terrain pack and protect the selected world's registry."""
from contextlib import contextmanager, nullcontext
from dataclasses import replace
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


def run_supervised(action, *, process_group=False):
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
            if process_group:
                os.setpgid(0, 0)
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            action()
        except BaseException as exc:
            os.write(2, f"innesto-run: {exc}\n".encode(errors="replace"))
        os._exit(1)
    if process_group:
        try:
            os.setpgid(pid, pid)
        except (ProcessLookupError, PermissionError):
            # The child can already have exec'd after setting its own group.
            pass
    handlers = {}
    def forward(signum, frame):
        try:
            if process_group:
                os.killpg(pid, signum)
            else:
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


def world_identity(profile, digest):
    return {"game": "a1.2.10", "platform": "linux-x86_64", "server": digest,
            "stock": profile["terrainPackSha256"], "baseCount": profile["terrainBaseCount"]}


def start(target, executable, digest, environment, mods, profile, arguments, launch, selected_peer=None,
          *, migrate=False, preview=False, remaps=None, backup=None, packages=None, solo_world=None, loader_path=None):
    offline = migrate or preview
    materials = {m.id: m for mod in mods for m in mod.terrain}
    solo = solo_world is not None
    if solo and (environment != "client" or selected_peer is not None):
        raise ValueError("--solo-world requires a physical client without a multiplayer peer")
    if solo and offline and arguments:
        raise ValueError("offline Solo operations take no native client arguments")
    if not solo and offline and (environment != "server" or len(arguments) != 2
                    or arguments[0] != "--data-dir"):
        raise ValueError("offline terrain operations require -- --data-dir WORLD on a server")
    if selected_peer is not None and (environment != "client" or not materials):
        raise ValueError("--terrain-peer requires a client with shared terrain packages")
    world = None
    if solo:
        from adapters.a1_2_10 import solo_host, terrain_solo
        world = solo_world.resolve()
        host_digest = solo_host.verify_host(Path(executable), profile.get("soloHostSha256"))
        registry_digest = terrain_solo.identity_digest(digest, host_digest)
    else:
        registry_digest = digest
    if environment == "server":
        world = routing.world_for_launch(arguments, bool(materials), REGISTRY)
    if world is not None and not materials and routing.protected(world, REGISTRY):
        if "terrainPackSha256" in profile and "terrainBaseCount" in profile:
            identity = world_identity(profile, registry_digest)
            with directory_lock(world) as lease:
                Registry(lease, identity).bind({}, remaps, migrate=offline)
        raise ValueError("terrain packages missing for this world; restore the recorded packages or use "
                         "--preview-terrain with the pinned terrain server profile and replacement packages")
    if not materials:
        if solo:
            raise ValueError("--solo-world requires shared terrain packages")
        if offline:
            raise ValueError("offline terrain operations require an existing managed world with terrain packages")
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
    if solo:
        game_dir = terrain_solo.game_directory(world, arguments, inputs=(cache, source_assets.parent, packages, loader_path, backup))
    if world is not None:
        if cache.resolve().is_relative_to(world):
            raise ValueError("terrain runtime cache must be outside the world")
        if offline and not world.is_dir():
            raise ValueError("terrain migration requires an existing managed world")
        world.mkdir(mode=0o700, parents=True, exist_ok=True)
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    available = {mid: material.aliases for mid, material in materials.items()}
    if backup is not None:
        destination = backup.resolve()
        for protected in (Path(executable).resolve().parent, packages.resolve(), cache.resolve()):
            if destination.is_relative_to(protected) or protected.is_relative_to(destination):
                raise ValueError("world backup must be separate from the game installation, packages and runtime cache")
    with (directory_lock(world) if world is not None else nullcontext()) as lease:
        if world is None:
            from adapters.a1_2_10.terrain_peer import peer_bindings, verify_peer
            peer = routing.peer_address(arguments, profile.get("terrainDashboardPort"), selected_peer)
            bindings = peer_bindings(*peer, available, base_count)
        else:
            registry = Registry(lease, world_identity(profile, registry_digest))
            bindings = registry.bind(available, remaps, migrate=offline)
            if solo:
                terrain_solo.validate_world(lease, world)
        ordered = [replace(materials[provider], id=mid) for mid, provider in bindings.items()]
        with tempfile.TemporaryDirectory(dir=cache, prefix="run-") as temporary:
            runtime = Path(temporary)
            if offline:
                legacy = {} if registry.schema == 1 else None
                candidates = terrain.stage_materials(stock, runtime / "pack", ordered, baseline,
                                                     legacy_receipts=legacy, providers=bindings)
                plan = registry.plan(candidates, migrate=True, legacy_receipts=legacy, bindings=bindings)
                check_world_path(world, lease)
                if preview:
                    for action in plan.actions:
                        print(action)
                    if not plan.changed:
                        print("Terrain registry already current.")
                    return 0
                if plan.provider_changes and backup is None:
                    raise ValueError("a terrain provider transfer requires --backup-world DIRECTORY")
                snapshot = nullcontext()
                if plan.changed and backup is not None:
                    from innesto_world_backup import locked_world_backup
                    snapshot = locked_world_backup(world, lease, backup)
                with snapshot:
                    check_world_path(world, lease)
                    registry.commit(plan)
                print("Terrain registry updated." if plan.changed else "Terrain registry already current.")
                return 0
            copy_assets(source_assets, runtime / "assets", stock)
            generated = runtime / "assets" / stock.relative_to(source_assets)
            generated.parent.chmod(generated.parent.stat().st_mode | 0o700)
            wire = {} if world is None else None
            candidates = terrain.stage_materials(stock, generated, ordered, baseline,
                                                 providers=bindings, wire_receipts=wire)
            if environment == "client":
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
                    verify_peer(*peer, wire, base_count, initial_order=list(bindings))
                    return run_supervised(lambda: launch(staged, str(image), arguments))
                check_world_path(world, lease)
                plan = registry.plan(candidates, bindings=bindings)
                if solo:
                    with solo_host.stage_solo_host(runtime, Path(executable), host_digest, world, lease):
                        registry.commit(plan)
                        terrain_solo.prepare_world(lease, world)

                        def exec_solo(fd, argv, env):
                            terrain_solo.exec_in_view(world, lease, game_dir, runtime, fd, argv[0], argv[1:], env)

                        return run_supervised(lambda: launch(staged, str(image), arguments, lease, exec_target=exec_solo),
                                              process_group=True)
                registry.commit(plan)
                arguments = routing.bind_world(arguments, world)

                def launch_world():
                    check_world_path(world, lease)
                    launch(staged, str(image), arguments, lease)

                return run_supervised(launch_world)
