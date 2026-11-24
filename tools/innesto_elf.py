"""Inspect Linux x86-64 ELF images through the descriptor used for launch."""
import os
import stat
import struct


ET_EXEC = 2
ET_DYN = 3
PT_DYNAMIC = 2
PT_INTERP = 3


def elf_segments(stream):
    """Return the ELF type and program segment types for a Linux x86-64 file."""
    fd = stream.fileno()
    size = os.fstat(fd).st_size
    header = os.pread(fd, 64, 0)
    if len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01":
        return None, set()
    elf_type, machine, version = struct.unpack_from("<HHI", header, 16)
    start = struct.unpack_from("<Q", header, 32)[0]
    header_size, stride, count = struct.unpack_from("<HHH", header, 52)
    if (machine, version, header_size, stride) != (62, 1, 64, 56) or start + stride * count > size:
        return None, set()
    table = os.pread(fd, stride * count, start)
    if len(table) != stride * count:
        return None, set()
    segments = set()
    for item in struct.iter_unpack("<IIQQQQQQ", table):
        segment, _, offset, _, _, length, _, _ = item
        if segment == PT_INTERP:
            if PT_INTERP in segments or not 2 <= length <= 4096 or offset + length > size:
                return None, set()
            interpreter = os.pread(fd, length, offset)
            if (not interpreter.startswith(b"/") or interpreter.count(b"\0") != 1
                    or os.path.basename(interpreter) != b"ld-linux-x86-64.so.2\0"):
                return None, set()
        segments.add(segment)
    return elf_type, segments


def verify_target_image(stream):
    elf_type, segments = elf_segments(stream)
    if elf_type not in (ET_EXEC, ET_DYN) or not {PT_DYNAMIC, PT_INTERP}.issubset(segments):
        raise ValueError("unsupported target executable format")
    mode = os.fstat(stream.fileno()).st_mode
    if mode & (stat.S_ISUID | stat.S_ISGID) or "security.capability" in os.listxattr(stream.fileno()):
        raise ValueError("unsupported target privilege mode")
