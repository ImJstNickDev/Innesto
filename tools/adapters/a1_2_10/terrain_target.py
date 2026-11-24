"""Resolve the a1.2.10 dedicated save and multiplayer endpoint used by the adapter."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def protected(world, registry):
    if os.path.lexists(world / registry):
        return True
    try:
        with os.scandir(world) as entries:
            return any(e.name.startswith((registry + ".backup-", registry + ".pending-")) for e in entries)
    except (FileNotFoundError, NotADirectoryError):
        return False


def opens_dedicated_world(arguments):
    # Recognize command modes in command position. A value supplied to an
    # option such as --name or --motd is not a utility command.
    modes = {"-h", "--help", "--gen-hashes", "--gen-selftest", "--export-skin-presets",
             "--column-diff", "--compact-world", "--verify-world", "--solo", "--ghost", "--terrain-worker"}
    args = arguments[1:] if arguments and not arguments[0].startswith("-") else arguments
    return not args or args[0] not in modes


def option(arguments, flag):
    positions = [i for i, value in enumerate(arguments) if value == flag]
    if not positions:
        return None
    if len(positions) != 1 or positions[0] + 1 == len(arguments) or arguments[positions[0] + 1].startswith("-"):
        raise ValueError(f"terrain cannot determine an unambiguous value for {flag}")
    return arguments[positions[0] + 1]


def server_world(arguments, active, registry):
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
            if protected(path, registry):
                return path
    return paths[0]


def peer_address(arguments, profile_port, selected_peer=None):
    direct = option(arguments, "--play")
    if selected_peer is not None and direct is not None and selected_peer != direct:
        raise ValueError("terrain peer must match the direct game connection")
    address = selected_peer or direct
    if not address:
        raise ValueError("terrain clients require --terrain-peer HOST:PORT or a direct --play HOST:PORT connection")
    parsed = urlsplit("//" + address)
    if (not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username is not None
            or parsed.password is not None):
        raise ValueError("invalid terrain server address")
    port = profile_port if profile_port is not None else (parsed.port or 24710) + 1
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid terrain dashboard port")
    return parsed.hostname, port


def world_for_launch(arguments, active, registry):
    for mode in ("--solo", "--ghost", "--terrain-worker", "--compact-world", "--verify-world"):
        operand = option(arguments, mode)
        if operand is not None:
            roots = [Path(operand)]
            if mode == "--verify-world" and arguments.index(mode) + 2 < len(arguments):
                roots.append(Path(arguments[arguments.index(mode) + 2]))
            if active or any(protected(root / entry, registry)
                                for root in roots for entry in (".", "cache")):
                raise ValueError("terrain registration requires a normal dedicated server")
    return server_world(arguments, active, registry)


def bind_world(arguments, world):
    arguments = list(arguments)
    if "--data-dir" in arguments:
        arguments[arguments.index("--data-dir") + 1] = str(world)
    else:
        arguments.extend(["--data-dir", str(world)])
    return arguments
