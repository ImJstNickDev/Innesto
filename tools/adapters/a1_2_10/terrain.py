"""Stage the a1.2.10 terrain pack for one private runtime."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import zlib

from .terrain_frames import stage_frames

COMPONENT = r"[a-z][a-z0-9_-]*"
MATERIAL_ID = re.compile(f"({COMPONENT}):({COMPONENT})", re.ASCII)
PREFIX = "innesto_"
NATIVE_FAMILIES = {"rock": "roche", "plant": "plante", "liquid": "liquide",
                   "glass": "verre", "foliage": "feuillage", "crop": "culture"}
# Saved terrain slots are unsigned 16-bit values on this version.
MAX_CATALOGUE_SIZE = 1 << 16
V1_PARAMETERS = "1.000000 0 roche"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_HEADER = struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0)
MAX_PNG_BYTES = 64 * 1024
ROW_BYTES = 1 + 32 * 4


def check_slot_count(base_count, additions):
    if type(base_count) is not int or base_count < 1 or base_count + additions > MAX_CATALOGUE_SIZE:
        raise ValueError("terrain catalogue exceeds the supported native slot range")


def original_pack(executable: Path) -> Path:
    return executable.parent / "assets" / "textures" / "packs" / "default"


def game_key(material_id: str) -> str:
    """Return the flat, operator-facing name. Only ASCII letters, digits and '_' reach the game."""
    match = MATERIAL_ID.fullmatch(material_id)
    if not match:
        raise ValueError(f"invalid terrain material ID {material_id!r}")
    namespace, local = (s.replace("_", "_u").replace("-", "_h") for s in match.groups())
    key = f"{PREFIX}{len(namespace)}_{namespace}_{local}"
    if len(f"ow_{key}.png") > 255:
        raise ValueError(f"encoded terrain material name is too long: {material_id!r}")
    return key


def _entries(root):
    for path in sorted(root.iterdir(), key=lambda p: os.fsencode(p.name)):
        mode = path.lstat().st_mode
        yield path, mode
        if stat.S_ISDIR(mode):
            yield from _entries(path)


def _stock_tree(stock, destination=None):
    if stock.is_symlink() or not stock.is_dir():
        raise ValueError("stock terrain pack must be a directory")
    digest = hashlib.sha256(b"Innesto terrain stock tree v1\0")
    for path, mode in _entries(stock):
        relative = path.relative_to(stock)
        name = os.fsencode(relative)
        output = destination / relative if destination else None
        if stat.S_ISDIR(mode):
            record = b"D"
            if output:
                output.mkdir(mode=0o700)
        elif stat.S_ISREG(mode):
            record = b"F"
            if output:
                shutil.copyfile(path, output)
            with (output or path).open("rb") as stream:
                file_digest = hashlib.file_digest(stream, "sha256").digest()
        else:
            raise ValueError("stock terrain pack contains a link or unsupported file")
        digest.update(record + struct.pack(">I", len(name)) + name)
        if record == b"F":
            digest.update(file_digest)
    return digest.hexdigest()


def stock_fingerprint(stock: Path) -> str:
    """Hash the entire stock tree, including paths and entry types, in deterministic order."""
    return _stock_tree(stock)


def _read_texture(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_PNG_BYTES + 1)
    if len(data) > MAX_PNG_BYTES or not data.startswith(PNG_SIGNATURE):
        raise ValueError("terrain texture must be a PNG of at most 64 KiB")

    offset = len(PNG_SIGNATURE)
    compressed = bytearray()
    while offset + 12 <= len(data):
        size, kind = struct.unpack_from(">I4s", data, offset)
        end = offset + 8 + size
        if end + 4 > len(data):
            raise ValueError("truncated terrain PNG chunk")
        body = data[offset + 8:end]
        if zlib.crc32(kind + body) != struct.unpack_from(">I", data, end)[0]:
            raise ValueError("invalid terrain PNG checksum")
        if offset == len(PNG_SIGNATURE):
            if kind != b"IHDR" or body != PNG_HEADER:
                raise ValueError("terrain PNG must be 32x32 non-interlaced 8-bit RGBA")
        elif kind == b"IDAT":
            compressed.extend(body)
        elif kind == b"IEND" and size == 0 and end + 4 == len(data):
            break
        else:
            raise ValueError("terrain PNG supports only IHDR, IDAT and IEND chunks")
        offset = end + 4
    else:
        raise ValueError("terrain PNG lacks a complete IEND")

    # All five PNG row filters are reversible on an arbitrary RGBA8 scanline.
    # Exactly one filter byte and 32 four-byte pixels must inflate for each row.
    expected = 32 * ROW_BYTES
    inflater = zlib.decompressobj()
    try:
        rows = inflater.decompress(compressed, expected + 1)
    except zlib.error as exc:
        raise ValueError("invalid terrain PNG compressed stream") from exc
    if (not inflater.eof or inflater.unused_data or len(rows) != expected
            or any(f > 4 for f in rows[::ROW_BYTES])):
        raise ValueError("invalid terrain PNG scanlines")
    return data, rows


def _texture_bytes(path):
    return _read_texture(path)[0]


def _opaque(rows):
    # PNG filters predict each channel from the same channel in adjacent pixels.
    # While testing for constant alpha, every previous alpha is known to be 255.
    for y in range(32):
        start = y * ROW_BYTES
        kind = rows[start]
        above = 255 if y else 0
        for x in range(32):
            left = 255 if x else 0
            # With a constant alpha, the Paeth predictor picks the available
            # opaque neighbour, or zero in the top-left corner.
            predictor = (0, left, above, (left + above) // 2, max(left, above))[kind]
            if rows[start + 4 + 4 * x] != 255 - predictor:
                return False
    return True


def content_fingerprint(texture: Path) -> str:
    """Hash the validated package texture as supplied by its author."""
    return hashlib.sha256(_texture_bytes(texture)).hexdigest()


def _tile_family(name):
    # Companion files share the base tile name. A new albedo must never turn
    # an existing file into its normal, roughness, emission or animation map.
    return re.sub(r"(?:_f(?:[1-9]|1[0-5])(?:_[nre])?|_[nre])$", "", name)


def _stock_names(descriptor, blocks):
    if not blocks.is_dir():
        raise ValueError("stock terrain pack lacks a blocks directory")
    resolutions = []
    declared = set()
    for line in descriptor.decode("utf-8").splitlines():
        fields = line.partition("#")[0].split()
        if not fields:
            continue
        if fields[0] == "resolution":
            resolutions.append(fields[1:])
        elif fields[0] == "tile":
            if len(fields) != 5 or not re.fullmatch(r"[A-Za-z0-9_-]+", fields[1]):
                raise ValueError("invalid stock terrain tile declaration")
            if not (blocks / f"{fields[1]}.png").is_file():
                raise ValueError("stock terrain pack lacks a declared tile image")
            name = fields[1].lower().removeprefix("ow_")
            if name in declared:
                raise ValueError("duplicate stock terrain material")
            declared.add(name)
    if resolutions != [["32"]] or not declared:
        raise ValueError("unsupported stock terrain descriptor")
    names = declared | {p.stem.lower().removeprefix("ow_") for p in blocks.iterdir()
                        if p.suffix.lower() == ".png"}
    return names | {_tile_family(key) for key in names}


def _receipt(stock_digest, parameters, names, frames):
    # Commit to the adapter contract and base assets in the PNG the peer can
    # actually fetch, without distributing the private stock fingerprint.
    if parameters == V1_PARAMETERS and not names and not frames:
        # Preserve existing worlds and the bytes consumed by version 1 peers.
        commitment = hashlib.sha256(b"Innesto terrain receipt v1\0" + bytes.fromhex(stock_digest))
    else:
        traits = [parameters, names]
        if frames:
            traits.append(frames)
        definition = json.dumps(traits, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8")
        commitment = hashlib.sha256(b"Innesto terrain receipt v2\0" + bytes.fromhex(stock_digest) + definition)
    return _png_receipt(commitment)


def _png_receipt(commitment):
    body = b"Innesto\0" + commitment.hexdigest().encode("ascii")
    return struct.pack(">I", len(body)) + b"tEXt" + body + struct.pack(">I", zlib.crc32(b"tEXt" + body))


def _definition_hash(fields):
    encoded = json.dumps(fields, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stage_materials(stock: Path, destination: Path, materials, expected_stock_sha256: str, *, legacy_receipts=None):
    """Stage one pack in the supplied slot order. Describe the exact bytes used."""
    if destination.resolve().is_relative_to(stock.resolve()):
        raise ValueError("runtime pack must be outside the stock pack")
    destination.mkdir(mode=0o700)
    try:
        digest = _stock_tree(stock, destination)
        if digest != expected_stock_sha256:
            raise ValueError("unsupported stock terrain pack fingerprint")
        descriptor = destination / "pack.txt"
        data = descriptor.read_bytes()
        blocks = destination / "blocks"
        occupied = _stock_names(data, blocks)
        result = {}
        lines = []
        for material in materials:
            key = game_key(material.id)
            if key in occupied or _tile_family(key) in occupied:
                raise ValueError(f"terrain material collision for {material.id!r}")
            occupied.add(key)
            texture, rows = _read_texture(material.texture)
            frames = stage_frames(blocks, key, material.frames, _texture_bytes)
            parameters = f"{material.tile_meters:.6f} {int(bool(frames))} {NATIVE_FAMILIES[material.family]}"
            # Insert the commitment immediately before IEND, after the complete IDAT stream.
            image = texture[:-12] + _receipt(digest, parameters, material.display_names, frames) + texture[-12:]
            with (blocks / f"ow_{key}.png").open("xb") as stream:
                stream.write(image)
            receipt = hashlib.sha256(image).hexdigest()
            if (legacy_receipts is not None and parameters != V1_PARAMETERS
                    and not frames and not material.display_names):
                # The first family/scale writer committed the native parameters directly.
                # Recover only a byte-exact match during explicit legacy enrollment.
                old = hashlib.sha256(b"Innesto terrain receipt v2\0" + bytes.fromhex(digest)
                                     + parameters.encode("ascii"))
                legacy_receipts[material.id] = hashlib.sha256(
                    texture[:-12] + _png_receipt(old) + texture[-12:]).hexdigest()
            appearance = [float(material.tile_meters), material.display_names, frames]
            visual = _definition_hash([*appearance, hashlib.sha256(texture).hexdigest()])
            rgb_editable = material.family == "rock" and not frames and _opaque(rows)
            result[material.id] = {
                "receipt": receipt,
                "gameplay": _definition_hash(["family", material.family]),
                "visual": visual,
                "visualPolicy": _definition_hash(["opaque-rock-rgb", *appearance] if rgb_editable
                                                 else ["exact-appearance", visual]),
            }
            lines.append(f"tile ow_{key} {parameters}\n")
        if lines:
            with descriptor.open("ab") as stream:
                if not data.endswith(b"\n"):
                    stream.write(b"\n")
                stream.write("".join(lines).encode("ascii"))
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise


def stage_pack(stock: Path, destination: Path, materials, expected_stock_sha256: str) -> dict[str, str]:
    """Return the wire receipts used by existing terrain peers."""
    staged = stage_materials(stock, destination, materials, expected_stock_sha256)
    return {mid: fields["receipt"] for mid, fields in staged.items()}
