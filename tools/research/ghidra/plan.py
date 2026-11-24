"""Make a scoped Ghidra study plan from operator-selected literal anchors on x86-64 ELF.

Correlates RIP-relative references with .eh_frame extents. These are candidates,
not a symbol table or a function prototype. All addresses in the plan are ELF VMAs.
"""

import argparse
import bisect
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path


def readelf(binary, *args):
    return subprocess.check_output(["readelf", *args, binary], text=True, env={"PATH": "/usr/bin", "LC_ALL": "C"})


def section(binary, name, sections):
    pattern = rf"\[\s*\d+\]\s+{re.escape(name)}\s+PROGBITS\s+(\w+)\s+(\w+)\s+(\w+)"
    match = re.search(pattern, sections)
    if not match:
        raise ValueError(f"{binary} has no expected {name} section")
    return tuple(int(value, 16) for value in match.groups())


def iter_output(command):
    with subprocess.Popen(command, stdout=subprocess.PIPE, text=True, env={"PATH": "/usr/bin", "LC_ALL": "C"}) as proc:
        yield from proc.stdout
        if proc.wait():
            raise RuntimeError(f"{command[0]} failed")


def build(binary, families):
    raw = binary.read_bytes()
    if raw[:6] != b"\x7fELF\x02\x01" or raw[18:20] != b"\x3e\x00":
        raise ValueError("expected little-endian x86-64 ELF")
    if not families:
        raise ValueError("no study families configured")
    all_anchors = set()
    for family, definition in families.items():
        anchors = set(definition["anchors"])
        if not 1 <= definition["minimum"] <= len(anchors):
            raise ValueError(f"invalid minimum for {family}")
        if any(not anchor or "\x00" in anchor for anchor in anchors):
            raise ValueError(f"invalid literal in {family}")
        all_anchors.update(anchors)
    sections = readelf(binary, "-WS")
    va, offset, length = section(binary, ".rodata", sections)
    rodata = raw[offset:offset + length]
    locations = {}
    for anchor in sorted(all_anchors):
        for match in re.finditer(re.escape(anchor.encode("ascii") + b"\x00"), rodata):
            locations[va + match.start()] = anchor
    scope_start, _, scope_length = section(binary, ".text", sections)
    span_pattern = re.compile(r"\bFDE\b.*?\bpc=([0-9a-f]+)\.\.([0-9a-f]+)")
    spans = []
    for line in iter_output(["readelf", "-wF", str(binary)]):
        match = span_pattern.search(line)
        if match:
            start, end = (int(x, 16) for x in match.groups())
            if scope_start <= start < end <= scope_start + scope_length:
                spans.append((start, end))
    spans = sorted(set(spans))
    if not spans:
        raise ValueError("no .text unwind extents")
    if any(right[0] < left[1] for left, right in zip(spans, spans[1:])):
        raise ValueError("overlapping unwind extents")
    starts = [start for start, _ in spans]
    groups = defaultdict(list)
    # GNU objdump resolves the actual RIP-relative destination after the comment.
    reference = re.compile(r"^\s*([0-9a-f]+):\s+lea\S*\s+[^#]*\(%rip\)[^#]*#\s*(?:0x)?([0-9a-f]+)\b")
    for line in iter_output(["objdump", "-dw", "-j", ".text", "--no-show-raw-insn", str(binary)]):
        if "%rip)" not in line or "#" not in line:
            continue
        match = reference.search(line)
        if not match:
            continue
        site, target = (int(x, 16) for x in match.groups())
        if target in locations:
            index = bisect.bisect_right(starts, site) - 1
            if index >= 0 and site < spans[index][1]:
                groups[spans[index]].append({"anchor": locations[target], "instruction": hex(site), "data": hex(target)})
    selected = []
    for (start, end), refs in sorted(groups.items()):
        anchors = {r["anchor"] for r in refs}
        labels = [name for name, rule in sorted(families.items())
                  if len(anchors.intersection(rule["anchors"])) >= rule["minimum"]]
        if labels:
            selected.append({"entry": hex(start), "end": hex(end), "families": labels, "references": refs})
    loads = re.findall(r"^\s*LOAD\s+0x\w+\s+0x(\w+)\b", readelf(binary, "-Wl"), re.M)
    build_id = re.search(r"Build ID: (\w+)", readelf(binary, "-n"))
    return {"schema": 1, "sha256": hashlib.sha256(raw).hexdigest(),
            "gnu_build_id": build_id.group(1) if build_id else None,
            "elf_base": hex(min(int(v, 16) for v in loads)), "families": families,
            "functions": selected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("anchors", type=Path, help="JSON object of {family: {anchors: [...], minimum: N}}")
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    plan = build(args.elf, json.loads(args.anchors.read_text()))
    args.plan.write_text(json.dumps(plan, indent=2) + "\n")


if __name__ == "__main__":
    main()
