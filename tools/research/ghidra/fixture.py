"""Verify scoped extraction on an original ELF. Outputs stay in the supplied work directory."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess

from plan import build


def load(path):
    return json.loads(path.read_text())


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True, help="new directory for generated files")
    parser.add_argument("--headless", type=Path, help="Ghidra support/analyzeHeadless")
    parser.add_argument("--pyghidra", action="store_true", help="also reopen the fixture project through PyGhidra")
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()
    if args.pyghidra and not args.headless:
        parser.error("--pyghidra requires --headless")
    work = args.work.resolve()
    work.mkdir(parents=True)
    here = Path(__file__).resolve().parent
    binary = work / "fixture.elf"
    subprocess.run([args.cc, "-O1", "-fno-builtin", "-fPIE", "-pie", "-fasynchronous-unwind-tables",
                    here/"fixture.c", "-o", binary], check=True)
    symbols = subprocess.check_output(["nm", "-n", binary], text=True)
    entry = int(re.search(r"^([\da-f]+) T record_pair$", symbols, re.M)[1], 16)
    subprocess.run(["strip", "--strip-all", binary], check=True)
    anchors = {"pair": {"anchors": ["fixture_cobalt", "fixture_amber"], "minimum": 2}}
    plan = build(binary, anchors)
    (function,) = plan["functions"]
    assert int(function["entry"], 16) == entry
    assert {ref["anchor"] for ref in function["references"]} == set(anchors["pair"]["anchors"])
    assert not build(binary, {"unused": {"anchors": ["fixture_absent"], "minimum": 1}})["functions"]
    if not args.headless:
        print("ELF fixture passed")
        return
    plan_file = work/"plan.json"
    output = work/"result.json"
    project = work/"project"
    project.mkdir()
    home = work/"home"
    temp = work/"tmp"
    home.mkdir()
    temp.mkdir()
    os.environ.update(HOME=str(home), TMPDIR=str(temp), XDG_CONFIG_HOME=str(home/".config"),
                      XDG_CACHE_HOME=str(home/".cache"), GHIDRA_HEADLESS_MAXMEM="1536M",
                      JAVA_TOOL_OPTIONS=os.environ.get("JAVA_TOOL_OPTIONS", "") +
                      f" -Duser.home={home} -Djava.io.tmpdir={temp} -XX:ActiveProcessorCount=2 -XX:-UsePerfData")
    headless = args.headless.resolve()
    base = [headless, project, "Fixture"]
    script = ["-noanalysis", "-max-cpu", "2", "-scriptPath", here, "-postScript",
              "InspectScopedFunctions.java", plan_file]
    # Ghidra continues after script exceptions. Require a fresh expected output for
    # success and check the precise script error when validating mismatched pins.
    plan_file.write_text(json.dumps(dict(plan, sha256="0" * 64)))
    rejected = subprocess.run([*base, "-import", binary, *script, output],
                              capture_output=True, text=True, check=False)
    if output.exists() or "Input SHA-256 differs" not in (rejected.stdout + rejected.stderr):
        raise RuntimeError("unexpected rejection result: " + (rejected.stdout + rejected.stderr)[-4000:])
    plan_file.write_text(json.dumps(plan))
    subprocess.run([*base, "-process", binary.name, *script, output], check=True)
    summary = load(output)
    assert summary["sha256"] == plan["sha256"]
    (verified,) = summary["functions"]
    assert verified["entry"] == function["entry"]
    assert verified["confirmed_references"] == function["references"]
    assert verified["decompiled"] and verified["basic_blocks"] >= 1 and verified["instructions"] >= 2
    narrower = copy.deepcopy(plan)
    narrower["functions"][0]["end"] = hex(entry + 1)
    narrower["functions"][0]["references"] = []
    plan_file.write_text(json.dumps(narrower))
    too_wide = work / "too-wide.json"
    rejected = subprocess.run([*base, "-process", binary.name, "-readOnly", *script, too_wide],
                              capture_output=True, text=True, check=False)
    if too_wide.exists() or "Saved function body exceeds" not in (rejected.stdout + rejected.stderr):
        raise RuntimeError("unexpected extent result: " + (rejected.stdout + rejected.stderr)[-4000:])
    plan_file.write_text(json.dumps(plan))
    if args.pyghidra:
        from verify_project import verify
        verified_project = verify(headless.parents[1], project, "Fixture", binary.name, plan, summary)
        assert verified_project["verified_references"] == len(function["references"])
        swapped = copy.deepcopy(plan)
        first, second = swapped["functions"][0]["references"]
        first["instruction"], second["instruction"] = second["instruction"], first["instruction"]
        forged = copy.deepcopy(summary)
        forged["functions"][0]["confirmed_references"] = swapped["functions"][0]["references"]
        try:
            verify(headless.parents[1], project, "Fixture", binary.name, swapped, forged)
        except ValueError as error:
            assert str(error) == "saved LEA targets a different literal address"
        else:
            raise AssertionError("swapped literal destinations passed verification")
        try:
            verify(headless.parents[1], project, "Fixture", binary.name, narrower, summary)
        except ValueError as error:
            assert str(error) == "saved function missing or outside selected unwind extent"
        else:
            raise AssertionError("oversize preexisting function passed verification")
    print("Ghidra fixture passed")


if __name__ == "__main__":
    run()
