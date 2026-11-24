"""Stage the contiguous extra albedo frames consumed by the a1.2.10 atlas."""

from collections.abc import Callable
import hashlib
from pathlib import Path
import re


MAX_FRAMES = 15


def stage_frames(blocks: Path, key: str, frames: tuple[Path, ...],
                 validate_texture: Callable[[Path], bytes]) -> list[str]:
    """Return ordered hashes of the exact validated frame bytes installed."""
    if not frames:
        return []
    if len(frames) > MAX_FRAMES:
        raise ValueError(f"terrain animation supports at most {MAX_FRAMES} extra frames")
    if not re.fullmatch(r"innesto_[a-z0-9_]+", key):
        raise ValueError("invalid encoded terrain animation key")
    stem = f"ow_{key}_f"
    if len(f"{stem}{len(frames)}.png") > 255:
        raise ValueError("encoded terrain material name is too long for its animation frames")

    # The renderer discovers following frames and their maps on disk. Reserve
    # all supported slots even when the authored sequence ends earlier.
    reserved = {f"{stem}{i}{suffix}.png" for i in range(1, MAX_FRAMES + 1)
                for suffix in ("", "_n", "_e", "_r")}
    if any(entry.name.lower() in reserved for entry in blocks.iterdir()):
        raise ValueError(f"terrain animation file collision for {key!r}")

    images = [validate_texture(frame) for frame in frames]
    created = []
    try:
        for i, image in enumerate(images, 1):
            path = blocks / f"{stem}{i}.png"
            with path.open("xb") as stream:
                created.append(path)
                stream.write(image)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return [hashlib.sha256(image).hexdigest() for image in images]
