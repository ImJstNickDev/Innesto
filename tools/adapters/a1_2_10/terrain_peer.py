"""Check the dedicated server's live terrain catalogue before a client launch."""

import hashlib
from http.client import HTTPConnection, HTTPException
import json

from innesto_packages import unique_keys
from .terrain import game_key, MAX_PNG_BYTES, PREFIX


TIMEOUT = 5
CATALOGUE_LIMIT = 4 * 1024 * 1024


def _fetch(host, port, path, limit):
    # http.client issues exactly this request; it never follows redirects or
    # reads proxy settings. Texture paths come only from the local adapter.
    connection = HTTPConnection(host, port, timeout=TIMEOUT)
    try:
        connection.request("GET", path)
        with connection.getresponse() as response:
            if response.status != 200:
                raise ValueError(f"terrain peer returned HTTP {response.status}")
            body = response.read(limit + 1)
            if len(body) > limit or (response.length is not None and response.length != 0):
                raise ValueError("invalid terrain peer response size")
            return body
    except (OSError, HTTPException) as exc:
        raise ValueError("could not read the terrain peer dashboard") from exc
    finally:
        connection.close()


def _catalogue(host, port):
    body = _fetch(host, port, "/api/info?planet=earth", CATALOGUE_LIMIT)
    try:
        catalogue = json.loads(body, object_pairs_hook=unique_keys)
    except (ValueError, RecursionError) as exc:
        raise ValueError("invalid terrain peer catalogue JSON") from exc
    rows = catalogue.get("materials") if isinstance(catalogue, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("invalid terrain peer material catalogue")

    ids = set()
    reported = {}
    for entry in rows:
        if not isinstance(entry, dict):
            raise ValueError("invalid terrain peer material record")
        index, key = entry.get("id"), entry.get("key")
        if (type(index) is not int or not 0 <= index < len(rows) or index in ids
                or not isinstance(key, str) or not key):
            raise ValueError("invalid or duplicate terrain peer material ID")
        ids.add(index)
        if key.lower().removeprefix("ow_").startswith(PREFIX):
            if not key.startswith(PREFIX) or key in reported:
                raise ValueError("unexpected or duplicate terrain peer material name")
            path = f"/pack/ow_{key}.png"
            if entry.get("texture") != path:
                raise ValueError("unexpected terrain peer texture path")
            reported[key] = index

    return len(rows), reported


def stock_count(host: str, port: int) -> int:
    """Measure the numeric ID range of a trusted stock-only server."""
    count, reported = _catalogue(host, port)
    if reported:
        raise ValueError("terrain stock catalogue already contains Innesto materials")
    return count


def verify_peer(host: str, port: int, materials: dict[str, str], base_count: int) -> None:
    """Require pinned stock slots, exact assigned IDs and matching texture receipts."""
    if type(base_count) is not int or base_count < 1:
        raise ValueError("invalid terrain peer stock material count")
    count, reported = _catalogue(host, port)
    expected = {game_key(mid): digest for mid, digest in materials.items()}
    if count != base_count + len(expected) or reported.keys() != expected.keys():
        raise ValueError("terrain peer catalogue differs from the pinned material set")
    for index, key in enumerate(expected, base_count):
        if reported.get(key) != index:
            raise ValueError("terrain peer material IDs differ from the local registry")
    for key, digest in expected.items():
        # The staged receipt is a single small ancillary chunk added to a
        # package PNG. The digest covers both the original bytes and the receipt.
        image = _fetch(host, port, f"/pack/ow_{key}.png", MAX_PNG_BYTES + 128)
        if hashlib.sha256(image).hexdigest() != digest:
            raise ValueError(f"terrain peer texture mismatch for {key!r}")
