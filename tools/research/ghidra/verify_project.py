"""Read a saved Ghidra project and independently verify the recorded image and reference sites."""
import argparse
import json
from pathlib import Path


def verify(install, project_dir, project_name, program_name, plan, report):
    import pyghidra

    pyghidra.start(install_dir=install)
    project = pyghidra.open_project(project_dir, project_name)
    try:
        with pyghidra.program_context(project, "/" + program_name) as program:
            digest = str(program.getExecutableSHA256()).lower()
            if digest != plan["sha256"] or digest != report["sha256"]:
                raise ValueError("saved program differs from expected image")
            matches = {row["entry"]: row for row in report["functions"]}
            if set(matches) != {row["entry"] for row in plan["functions"]} or len(matches) != len(report["functions"]):
                raise ValueError("report differs from study plan")
            memory = program.getMemory()
            base = program.getImageBase()
            elf_base = int(plan["elf_base"], 16)
            for row in plan["functions"]:
                record = matches[row["entry"]]
                entry = base.add(int(row["entry"], 16) - elf_base)
                if not row.get("sites_only") and program.getFunctionManager().getFunctionAt(entry) is None:
                    raise ValueError("missing function in saved project")
                if record["confirmed_references"] != row["references"]:
                    raise ValueError("headless Ghidra did not confirm all planned references")
                for ref in row["references"]:
                    site = base.add(int(ref["instruction"], 16) - elf_base)
                    data = base.add(int(ref["data"], 16) - elf_base)
                    instruction = program.getListing().getInstructionAt(site)
                    if instruction is None or str(instruction.getMnemonicString()).upper() != "LEA":
                        raise ValueError("saved reference site is not a decoded LEA")
                    for i, byte in enumerate(ref["anchor"].encode("ascii") + b"\0"):
                        if memory.getByte(data.add(i)) & 255 != byte:
                            raise ValueError("saved literal bytes disagree")
            return {"project": project_name, "image_sha256": digest, "functions_or_extents": len(matches),
                    "verified_references": sum(len(f["references"]) for f in plan["functions"])}
    finally:
        project.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("install", type=Path)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("project")
    parser.add_argument("program")
    parser.add_argument("plan", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.install, args.project_dir, args.project, args.program,
                            json.loads(args.plan.read_text()), json.loads(args.report.read_text()))))


if __name__ == "__main__":
    main()
