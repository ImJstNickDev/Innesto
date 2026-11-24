"""Check bounded Ghidra BSim and VT against two stripped, original Linux PIEs."""
import argparse
import csv
import hashlib
import os
from pathlib import Path
import platform
import subprocess
import tempfile

SCRIPTS = Path(__file__).resolve().parent
NAMES = {"tone", "limit", "count_bits"}


def make_image(root, name, variant):
    binary = root / name
    subprocess.run(["cc", "-O2", "-fPIE", "-pie", "-o", binary,
                    f"-DVARIANT={variant}", SCRIPTS / "fixture.c"], check=True)
    entries = {}
    for line in subprocess.check_output(["nm", "-S", "--defined-only", binary], text=True).splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[3] in NAMES:
            address, size = (int(value, 16) for value in fields[:2])
            entries[fields[3]] = (address, address + size)
    if entries.keys() != NAMES:
        raise ValueError("Fixture symbols missing before stripping")
    selections = root / f"{name}.tsv"
    selections.write_text("".join(f"{start:#x}\t{end:#x}\n" for start, end in entries.values()))
    subprocess.run(["strip", "--strip-all", binary], check=True)
    if ".symtab" in subprocess.check_output(["readelf", "-SW", binary], text=True):
        raise ValueError("Fixture retained its symbol table")
    # Execute only the binaries built above. The independent oracle uses public inputs.
    for x in (0, 1, 13, 22, 23, 32, 0x12345678, 0xFFFFFFFF):
        output = subprocess.check_output([binary, str(x)], text=True)
        tone = x
        for i in range(5):
            tone = ((tone ^ (tone >> 9)) * 33 + i) & 0xFFFFFFFF
        limit = x * 3 + variant if x < 23 else (x >> 2) ^ 55
        if list(map(int, output.split())) != [tone, limit, x.bit_count()]:
            raise ValueError("Stripped fixture disagrees with the source oracle")
    return entries


def headless(ghidra, root, name, *options):
    # The install can choose its own compatible JDK from JAVA_HOME or PATH.
    home = root / "home"
    env = dict(os.environ, HOME=str(home), XDG_CACHE_HOME=str(home / ".cache"),
               XDG_CONFIG_HOME=str(home / ".config"), GHIDRA_HEADLESS_MAXMEM="1G")
    java_flags = env.get("JAVA_TOOL_OPTIONS", "")
    env["JAVA_TOOL_OPTIONS"] = f'{java_flags} "-Duser.home={home}" -XX:ActiveProcessorCount=2'
    with (root / f"{name}.log").open("w") as log:
        result = subprocess.run([ghidra / "support/analyzeHeadless", root / "projects", "Fixture",
                                 "-noanalysis", "-max-cpu", "2", "-scriptPath", SCRIPTS,
                                 "-scriptlog", root / "script.log", "-log", root / "ghidra.log", *options],
                                cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
    messages = (root / f"{name}.log").read_text(errors="replace")
    if result.returncode or "ERROR " in messages:
        raise RuntimeError(f"Ghidra failed during {name} (see {name}.log)")


def check(ghidra, root):
    for name in ("projects", "home"):
        (root / name).mkdir()
    source = make_image(root, "alpha", 7)
    target = make_image(root, "beta", 11)
    if source["tone"][0] == target["tone"][0]:
        raise ValueError("The fixture pair must exercise different entry offsets")
    if hashlib.sha256((root / "alpha").read_bytes()).digest() == hashlib.sha256((root / "beta").read_bytes()).digest():
        raise ValueError("Expected two distinct stripped images")
    for image in ("alpha", "beta"):
        headless(ghidra, root, image, "-import", root / image,
                 "-postScript", "DefineSelection.java", root / f"{image}.tsv")
    headless(ghidra, root, "compare", "-process", "alpha", "-postScript",
             "CompareSelection.java", "/beta", root / "alpha.tsv", root / "beta.tsv", root, "Selection")
    if not (root / "complete").is_file():
        raise ValueError("Missing headless completion marker (see compare.log)")
    with (root / "bsim.tsv").open() as stream:
        bsim = {(int(r["source"], 16), int(r["destination"], 16)): float(r["similarity"])
                for r in csv.DictReader(stream, delimiter="\t")}
    with (root / "vt.tsv").open() as stream:
        vt = {(int(r["source"], 16), int(r["destination"], 16), r["correlator"])
              for r in csv.DictReader(stream, delimiter="\t")}
    a, b = source["tone"][0], target["tone"][0]
    unrelated = target["count_bits"][0]
    exact = "Exact Function Bytes Match"
    if (len(bsim) != len(source) * len(target) or bsim[a, b] < .9999 or
            bsim[a, unrelated] >= bsim[a, b] or (a, b, exact) not in vt or
            any(left == a and right == unrelated for left, right, _ in vt)):
        raise ValueError("Fixture positive or unrelated control failed")
    # Known near-miss: the oracle above distinguishes these functions for x < 23.
    if (source["limit"][0], target["limit"][0], exact) in vt:
        raise ValueError("Different function bytes matched the exact-byte correlator")
    print(f"Original fixture verified: {len(bsim)} BSim comparisons, {len(vt)} VT associations")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ghidra", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="retain results in this new directory")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("the native fixture targets Linux x86-64")
    ghidra = args.ghidra.resolve(strict=True)
    if args.output:
        root = args.output.resolve()
        root.mkdir(mode=0o700)
        check(ghidra, root)
    else:
        with tempfile.TemporaryDirectory(prefix="innesto-match-") as tmp:
            check(ghidra, Path(tmp))


if __name__ == "__main__":
    main()
