"""Collect private Solo terrain pins from a trusted installation and its stock run."""
import hashlib
import os
from pathlib import Path
import re

from innesto_elf import verify_target_image
from . import terrain
from .solo_host import _host_image


def stock_count(log, host):
    # The HUD counts usable icons. Only the terrain renderer reports the full
    # native slot range. Require a single stock client session with its own host.
    client = re.compile(r"\[client\] \[t0\] Openworld Client (\S+)")
    component = re.compile(r"^\S+ \S+ \[INFO *\] \[(solo|lod)\] \[t0\] (.*)")
    count_pattern = re.compile(r"\((\d+) (?:materiaux|matériaux|materials),")
    expected_child = "(" + os.fspath(host) + ")"
    versions = []
    counts = set()
    selected_host = ready = False
    with log.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith("Innesto "):
                raise ValueError("record an unmodified client session for the Solo reference")
            banner = client.search(line)
            if banner:
                versions.append(banner[1])
            record = component.match(line)
            if not record:
                continue
            group, message = record.groups()
            if group == "solo":
                if expected_child in message:
                    selected_host = True
                if selected_host and "OW-SOLO ready " in message and " version=a1.2.10 " in message:
                    ready = True
            elif ready and (match := count_pattern.search(message)):
                counts.add(int(match[1]))
    if versions != ["a1.2.10"] or not ready or len(counts) != 1:
        raise ValueError("capture one stock Solo session from this installation through in-world terrain loading")
    count = counts.pop()
    terrain.check_slot_count(count, 0)
    return count


def reference(executable, expected, log):
    client = Path(executable).resolve(strict=True)
    with client.open("rb") as source:
        verify_target_image(source)
        if hashlib.file_digest(source, "sha256").hexdigest() != expected:
            raise ValueError("unsupported target fingerprint")
    with _host_image(client) as source:
        helper = hashlib.file_digest(source, "sha256").hexdigest()
    return {"soloHostSha256": helper, "terrainPackSha256": terrain.stock_fingerprint(terrain.original_pack(client)),
            "terrainBaseCount": stock_count(log, client.with_name("owserver"))}
