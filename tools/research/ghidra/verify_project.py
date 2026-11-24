"""Read a saved Ghidra project and independently verify the recorded image and reference sites."""
import argparse
import json
from pathlib import Path


def verify_target(instruction, expected):
    # Decode the RIP-relative x86-64 LEA independently of the importer. Its
    # signed disp32 counts from the end of the instruction. REX, segment and
    # operand-size prefixes do not change that base; address-size override does.
    raw = bytes(int(value) & 255 for value in instruction.getBytes())
    prefix = raw[:-6]
    if (len(raw) < 6 or raw[-6] != 0x8d or raw[-5] & 0xc7 != 0x05
            or any(value not in (0x26, 0x2e, 0x36, 0x3e, 0x64, 0x65, 0x66)
                   and not 0x40 <= value <= 0x4f for value in prefix)):
        raise ValueError("reference site is not a RIP-relative LEA")
    displacement = int.from_bytes(raw[-4:], "little", signed=True)
    if instruction.getAddress().add(len(raw) + displacement) != expected:
        raise ValueError("saved LEA targets a different literal address")


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
            from ghidra.program.model.address import AddressSet
            for row in plan["functions"]:
                record = matches[row["entry"]]
                entry = base.add(int(row["entry"], 16) - elf_base)
                end = base.add(int(row["end"], 16) - elf_base - 1)
                if int(record["ghidra_entry"], 16) != entry.getOffset():
                    raise ValueError("report entry disagrees with saved project")
                scope = AddressSet(entry, end)
                if not row.get("sites_only"):
                    function = program.getFunctionManager().getFunctionAt(entry)
                    if function is None or not scope.contains(function.getBody()):
                        raise ValueError("saved function missing or outside selected unwind extent")
                if record["confirmed_references"] != row["references"]:
                    raise ValueError("headless Ghidra did not confirm all planned references")
                for ref in row["references"]:
                    site = base.add(int(ref["instruction"], 16) - elf_base)
                    data = base.add(int(ref["data"], 16) - elf_base)
                    instruction = program.getListing().getInstructionAt(site)
                    if instruction is None or str(instruction.getMnemonicString()).upper() != "LEA":
                        raise ValueError("saved reference site is not a decoded LEA")
                    if not scope.contains(site, instruction.getMaxAddress()):
                        raise ValueError("saved reference site falls outside selected unwind extent")
                    verify_target(instruction, data)
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
