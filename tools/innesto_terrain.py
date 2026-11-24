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
from urllib.parse import urlsplit

from adapters.a1_2_10 import terrain
from innesto_packages import unique_keys


REGISTRY = "innesto-terrain-v1.json"


def option(arguments, flag):
    positions = [i for i, value in enumerate(arguments) if value == flag]
    if not positions:
        return None
    if len(positions) != 1 or positions[0] + 1 == len(arguments) or arguments[positions[0] + 1].startswith("-"):
        raise ValueError(f"terrain cannot determine an unambiguous value for {flag}")
    return arguments[positions[0] + 1]


def server_world(arguments, active):
    """Use the server's data root. Cover alternate config-relative roots when checking legacy launches."""
    data = option(arguments, "--data-dir")
    if data:
        return Path(data).resolve()
    instance = Path(arguments[0]) if arguments and not arguments[0].startswith("-") else Path.cwd()
    config = Path(option(arguments, "--config") or instance)
    if config.is_dir():
        config = config / "server.json"
    configured = "owserver_data"
    if config.is_file():
        try:
            configured = json.loads(config.read_bytes()).get("dataDir", configured)
            if not isinstance(configured, str) or not configured:
                raise ValueError("invalid data directory")
        except (AttributeError, UnicodeError, ValueError):
            if active:
                raise ValueError("terrain requires a valid server config or an explicit --data-dir") from None
            configured = "owserver_data"
    paths = [(base / configured).resolve() for base in (Path.cwd(), config.parent, instance)]
    if active and len(set(paths)) > 1:
        raise ValueError("supply --data-dir for terrain with a separate server instance or config directory")
    if not active:
        for path in paths:
            if os.path.lexists(path / REGISTRY):
                return path
    return paths[0]


@contextmanager
def world_registry(world, receipt):
    world.mkdir(parents=True, exist_ok=True)
    with directory_lock(world):
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
        yield


@contextmanager
def directory_lock(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another Innesto launcher holds this terrain world") from None
        # A surviving game must retain the lease if its supervisor is killed.
        os.set_inheritable(fd, True)
        yield
    finally:
        os.close(fd)


def peer_address(arguments, profile_port):
    address = option(arguments, "--play")
    if not address:
        raise ValueError("terrain clients require a direct --play HOST:PORT connection")
    parsed = urlsplit("//" + address)
    if (not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username is not None
            or parsed.password is not None):
        raise ValueError("invalid terrain server address")
    port = profile_port if profile_port is not None else (parsed.port or 24710) + 1
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid terrain dashboard port")
    return parsed.hostname, port


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


def start(target, executable, digest, environment, mods, profile, arguments, launch):
    materials = sorted((m for mod in mods for m in mod.terrain), key=lambda m: m.id)
    world = None
    if environment == "server":
        for mode in ("--solo", "--ghost", "--terrain-worker", "--compact-world", "--verify-world"):
            operand = option(arguments, mode)
            if operand is not None:
                roots = [Path(operand)]
                if mode == "--verify-world" and arguments.index(mode) + 2 < len(arguments):
                    roots.append(Path(arguments[arguments.index(mode) + 2]))
                if materials or any(os.path.lexists(root / entry / REGISTRY)
                                    for root in roots for entry in (".", "cache")):
                    raise ValueError("terrain registration requires a normal dedicated server")
        world = server_world(arguments, bool(materials))
        if not materials and os.path.lexists(world / REGISTRY):
            raise ValueError("terrain packages missing for this world; restore them before opening it")
    if not materials:
        if "terrainPackSha256" in profile or "terrainBaseCount" in profile:
            raise ValueError("terrain profile requires its shared material packages")
        # A package-free launch racing a first material launch must use the same
        # lease. Keep legacy utility invocations from creating new save paths.
        if world is not None and (world.is_dir() or "--data-dir" in arguments):
            world.mkdir(parents=True, exist_ok=True)
            with directory_lock(world):
                if os.path.lexists(world / REGISTRY):
                    raise ValueError("terrain packages missing for this world")
                launch(target, executable, arguments)
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
        image = runtime / Path(executable).name
        target.seek(0)
        with image.open("xb") as dest:
            shutil.copyfileobj(target, dest)
        image.chmod(0o500)
        with image.open("rb") as staged:
            if hashlib.file_digest(staged, "sha256").hexdigest() != digest:
                raise ValueError("staged terrain target identity changed")
            def play():
                launch(staged, str(image), arguments)
            if world is None:
                from adapters.a1_2_10.terrain_peer import verify_peer
                verify_peer(*peer_address(arguments, profile.get("terrainDashboardPort")), textures, base_count)
                return run_supervised(play)
            arguments = list(arguments)
            if "--data-dir" in arguments:
                arguments[arguments.index("--data-dir") + 1] = str(world)
            else:
                arguments.extend(["--data-dir", str(world)])
            receipt = {"schema": 1, "game": "a1.2.10", "platform": "linux-x86_64",
                       "server": digest, "stock": baseline, "baseCount": base_count,
                       "materials": [[key, value] for key, value in textures.items()]}
            with world_registry(world, receipt):
                return run_supervised(play)
