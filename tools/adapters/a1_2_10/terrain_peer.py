"""Check the dedicated server's live terrain catalogue before a client launch."""

import hashlib
from http.client import HTTPConnection, HTTPException
import json

from innesto_packages import unique_keys
from innesto_registry import provider_index
from .terrain import check_slot_count, game_key, MAX_CATALOGUE_SIZE, MAX_PNG_BYTES, PREFIX


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


def _catalogue(host, port, limit=CATALOGUE_LIMIT):
    body = _fetch(host, port, "/api/info?planet=earth", limit)
    try:
        catalogue = json.loads(body, object_pairs_hook=unique_keys)
    except (ValueError, RecursionError) as exc:
        raise ValueError("invalid terrain peer catalogue JSON") from exc
    rows = catalogue.get("materials") if isinstance(catalogue, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CATALOGUE_SIZE:
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


def peer_order(host: str, port: int, material_ids, base_count: int) -> list[str]:
    return list(peer_bindings(host, port, {mid: () for mid in material_ids}, base_count))


def peer_bindings(host, port, available, base_count):
    """Bind one local provider to each persistent slot advertised by the server."""
    if type(base_count) is not int or base_count < 1:
        raise ValueError("invalid terrain peer stock material count")
    owners = provider_index(available)
    by_key = {game_key(mid): mid for mid in owners}
    check_slot_count(base_count, len(available))
    limit = CATALOGUE_LIMIT + sum(1024 + 4 * len(key) for key in by_key)
    count, reported = _catalogue(host, port, limit)
    if count != base_count + len(available) or len(reported) != len(available) or reported.keys() - by_key.keys():
        raise ValueError("terrain peer catalogue differs from the pinned material set")
    ordered = sorted(reported, key=reported.__getitem__)
    if any(reported[key] != index for index, key in enumerate(ordered, base_count)):
        raise ValueError("terrain peer material IDs overlap the pinned stock slots")
    bindings = {by_key[key]: owners[by_key[key]] for key in ordered}
    if set(bindings.values()) != set(available):
        raise ValueError("terrain peer slots do not match the installed providers")
    return bindings


def verify_peer(host: str, port: int, materials: dict[str, str], base_count: int, *, initial_order=None) -> None:
    """Recheck the staged order and served texture receipts immediately before launch."""
    if initial_order is None:
        initial_order = peer_order(host, port, materials, base_count)
    if initial_order != list(materials):
        raise ValueError("terrain peer material IDs differ from the local registry")
    for mid, digest in materials.items():
        key = game_key(mid)
        # The staged receipt is a single small ancillary chunk added to a
        # package PNG. The digest covers both the original bytes and the receipt.
        image = _fetch(host, port, f"/pack/ow_{key}.png", MAX_PNG_BYTES + 128)
        if hashlib.sha256(image).hexdigest() != digest:
            raise ValueError(f"terrain peer texture mismatch for {key!r}")
    if peer_order(host, port, materials, base_count) != initial_order:
        raise ValueError("terrain peer material IDs changed during preflight")
