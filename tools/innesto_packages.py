"""Read native mod packages and resolve their initialization order."""

from dataclasses import dataclass, field
import heapq
import json
from pathlib import Path
import re
import stat


from adapters.a1_2_10.terrain import game_key
from adapters.a1_2_10.terrain_names import validate_display_names


MOD_ID = re.compile(r"[a-z][a-z0-9_-]*")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}")
MANIFEST = "innesto.mod.json"
REQUIRED_FIELDS = {"schemaVersion", "id", "version", "game", "api", "environment", "entrypoint"}


@dataclass(frozen=True)
class TerrainMaterial:
    id: str
    texture: Path
    family: str = "rock"
    tile_meters: float = 1.0
    display_names: dict[str, str] = field(default_factory=dict)
    frames: tuple[Path, ...] = ()
    aliases: tuple[str, ...] = ()


@dataclass
class Package:
    mod_id: str
    version: str
    depends: dict[str, str]
    entrypoint: Path
    directory: Path
    folder: str
    environment: str
    api: int
    terrain: tuple[TerrainMaterial, ...]


@dataclass
class SelectedMod:
    library: Path
    mod_id: str
    api: int
    terrain: tuple[TerrainMaterial, ...] = ()


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def relative_path(relative):
    if not isinstance(relative, str) or not relative or "\0" in relative:
        raise ValueError("expected a nonempty relative file path without NUL")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path {relative!r} must be relative to the package without '..'")
    return path


def confined_file(root, relative, label="package"):
    resolved = (root / relative).resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"{str(relative)!r} must resolve to a regular file inside the {label}")
    return resolved


def check_fields(data, name, required, optional=frozenset()):
    if not isinstance(data, dict):
        raise ValueError(f"{name} must be a JSON object")
    missing = sorted(required - data.keys())
    if missing:
        raise ValueError(f"{name}: missing field(s): {', '.join(missing)}")
    unknown = sorted(data.keys() - required - optional)
    if unknown:
        raise ValueError(f"{name}: unknown field(s): {', '.join(unknown)}")


def read_frames(assets, frames, field):
    if not isinstance(frames, list) or len(frames) > 15:
        raise ValueError(f"{field}.frames must be an array of at most 15 texture paths")
    try:
        return tuple(confined_file(assets, relative_path(frame), "assets directory") for frame in frames)
    except (ValueError, OSError, RuntimeError) as exc:
        raise ValueError(f"{field}.frames: {file_error(exc)}") from exc


def read_terrain(content, directory, mod_id):
    check_fields(content, "content", {"version", "assets", "terrain"})
    if type(content["version"]) is not int or content["version"] not in (1, 2, 3):
        raise ValueError("content.version must be the integer 1, 2 or 3")
    if not isinstance(content["terrain"], list):
        raise ValueError("content.terrain must be an array")
    try:
        assets = (directory / relative_path(content["assets"])).resolve(strict=True)
        if assets == directory or not assets.is_relative_to(directory) or not assets.is_dir():
            raise ValueError("expected a subdirectory inside the package")
    except (ValueError, OSError, RuntimeError) as exc:
        raise ValueError(f"invalid content.assets: {file_error(exc)}") from exc

    materials = {}
    prefix = mod_id + ":"
    for index, item in enumerate(content["terrain"]):
        field = f"content.terrain[{index}]"
        optional = {"family", "tileMeters", "displayNames", "frames"} if content["version"] >= 2 else set()
        if content["version"] == 3:
            optional.add("aliases")
        check_fields(item, field, {"id", "texture"}, optional)
        family = item.get("family", "rock")
        if family not in ("rock", "plant", "liquid", "glass", "foliage", "crop"):
            raise ValueError(f"{field}.family must be rock, plant, liquid, glass, foliage or crop")
        scale = item.get("tileMeters", 1)
        if type(scale) not in (float, int) or scale not in (0.25, 0.5, 1, 1.5, 2, 2.5):
            raise ValueError(f"{field}.tileMeters must be one of 0.25, 0.5, 1, 1.5, 2 or 2.5")
        names = validate_display_names(item.get("displayNames", {}))
        material_id = item["id"]
        if (not isinstance(material_id, str) or not material_id.startswith(prefix)
                or not matches(MOD_ID, material_id[len(prefix):])):
            raise ValueError(f"{field}.id must be {prefix}{MOD_ID.pattern}")
        game_key(material_id)
        if material_id in materials:
            raise ValueError(f"duplicate terrain id {material_id!r}")
        try:
            texture = confined_file(assets, relative_path(item["texture"]), "assets directory")
        except (ValueError, OSError, RuntimeError) as exc:
            raise ValueError(f"invalid texture for {material_id!r}: {file_error(exc)}") from exc
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
            raise ValueError(f"{field}.aliases must be an array of namespaced identifiers")
        for alias in aliases:
            game_key(alias)
        if material_id in aliases or len(set(aliases)) != len(aliases):
            raise ValueError(f"{field}.aliases contains a duplicate or the material itself")
        frames = read_frames(assets, item.get("frames", []), field)
        materials[material_id] = TerrainMaterial(material_id, texture, family, float(scale), names, frames, tuple(aliases))
    return tuple(materials.values())


def read_package(directory, folder):
    manifest = confined_file(directory, MANIFEST)
    data = json.loads(manifest.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    check_fields(data, "manifest", REQUIRED_FIELDS, {"depends", "content"})
    if type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1:
        raise ValueError("schemaVersion must be the integer 1")
    if type(data["api"]) is not int or data["api"] not in (1, 2):
        raise ValueError("api must be the integer 1 or 2")
    if data["game"] != "a1.2.10":
        raise ValueError("game must be 'a1.2.10'")
    if data["environment"] not in ("server", "client", "shared"):
        raise ValueError("environment must be 'client', 'server' or 'shared'")
    if not matches(MOD_ID, data["id"]):
        raise ValueError(f"id must match {MOD_ID.pattern}")
    if not matches(VERSION, data["version"]):
        raise ValueError("version must be major.minor.patch with no leading zeroes")
    depends = data.get("depends", {})
    if not isinstance(depends, dict):
        raise ValueError("depends must be an object")
    for key, value in depends.items():
        if not matches(MOD_ID, key):
            raise ValueError(f"invalid dependency id {key!r}")
        if value != "*" and not matches(VERSION, value):
            raise ValueError(f"dependency {key!r} needs '*' or an exact major.minor.patch version")
    try:
        entrypoint = relative_path(data["entrypoint"])
    except (ValueError, RuntimeError, OSError) as exc:
        raise ValueError(f"invalid entrypoint {data['entrypoint']!r}: {file_error(exc)}") from exc
    terrain = ()
    if "content" in data:
        if data["environment"] != "shared":
            raise ValueError("content requires environment 'shared'")
        terrain = read_terrain(data["content"], directory, data["id"])
    return Package(data["id"], data["version"], depends, entrypoint, directory, folder,
                   data["environment"], data["api"], terrain)


def file_error(exc):
    # Identify the affected package without exposing the absolute local layout.
    return exc.strerror if isinstance(exc, OSError) else str(exc)


def cycle_path(packages, blocked):
    current = min(blocked)
    trace = []
    positions = {}
    while current not in positions:
        positions[current] = len(trace)
        trace.append(current)
        current = min(packages[current].depends.keys() & blocked)
    return " -> ".join([*trace[positions[current]:], current])


def ordered_ids(packages, installed, environment):
    remaining = {}
    dependents = {name: [] for name in packages}
    for name, package in packages.items():
        remaining[name] = len(package.depends)
        for dep, requirement in package.depends.items():
            if dep not in packages:
                if dep in installed:
                    raise ValueError(f"{name!r} requires {dep!r}, unavailable on {environment}")
                raise ValueError(f"{name!r} requires missing mod {dep!r}")
            version = packages[dep].version
            if requirement not in ("*", version):
                raise ValueError(f"{name!r} requires {dep!r} version {requirement}, found {version}")
            dependents[dep].append(name)

    ready = [name for name, count in remaining.items() if count == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        name = heapq.heappop(ready)
        ordered.append(name)
        for dependent in dependents[name]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                heapq.heappush(ready, dependent)
    if len(ordered) != len(packages):
        blocked = {name for name, count in remaining.items() if count}
        raise ValueError(f"dependency cycle: {cycle_path(packages, blocked)}")
    return ordered


def select_packages(root, environment):
    if environment not in ("client", "server"):
        raise ValueError("target environment must be 'client' or 'server'")
    if not root.is_dir():
        raise ValueError("--mods-dir must name an existing directory")
    root = root.resolve(strict=True)
    packages = {}
    for candidate in sorted(root.iterdir()):
        try:
            try:
                mode = candidate.stat().st_mode
            except FileNotFoundError:
                if candidate.is_symlink():
                    continue
                raise
            if not stat.S_ISDIR(mode):
                continue
            directory = candidate.resolve(strict=True)
            if directory == root or not directory.is_relative_to(root):
                raise ValueError("package directory resolves outside its location under --mods-dir")
            package = read_package(directory, candidate.name)
        except (ValueError, RuntimeError, OSError) as exc:
            raise ValueError(f"{candidate.name!r}/{MANIFEST}: {file_error(exc)}") from exc
        if package.mod_id in packages:
            other = packages[package.mod_id]
            raise ValueError(f"duplicate mod id {package.mod_id!r} in {other.folder!r} and {candidate.name!r}")
        packages[package.mod_id] = package

    active = {name: package for name, package in packages.items()
              if package.environment in ("shared", environment)}
    libraries = {}
    selected = []
    for name in ordered_ids(active, packages, environment):
        package = active[name]
        try:
            library = confined_file(package.directory, package.entrypoint)
            entry = library.stat()
        except (ValueError, RuntimeError, OSError) as exc:
            raise ValueError(f"{package.folder!r}/{MANIFEST}: invalid entrypoint "
                             f"{str(package.entrypoint)!r}: {file_error(exc)}") from exc
        identity = (entry.st_dev, entry.st_ino)
        if identity in libraries:
            raise ValueError(f"{name!r} and {libraries[identity]!r} use the same entrypoint file")
        libraries[identity] = name
        selected.append(SelectedMod(library, name, package.api, package.terrain))
    return selected


def discover_mods(root, environment="server"):
    """Return the ordered library paths for a physical environment."""
    return [mod.library for mod in select_packages(root, environment)]
