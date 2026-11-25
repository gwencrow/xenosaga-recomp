"""Preflight for the pinned PS2Recomp dense function registrar."""

import argparse
import re
import struct
import subprocess
from pathlib import Path


def elf_entry(path):
    with path.open("rb") as stream:
        header = stream.read(52)
    if (len(header) != 52 or header[:7] != b"\x7fELF\x01\x01\x01"
            or struct.unpack_from("<HHI", header, 16) != (2, 8, 1)):
        raise ValueError(f"{path}: expected a little-endian ELF32 MIPS executable")
    entry, = struct.unpack_from("<I", header, 24)
    if not entry or entry % 4:
        raise ValueError(f"{path}: invalid guest ELF entry {entry:#x}")
    return entry


def entry_slot(source, entry, path):
    """Validate the emitter's initializer rows and return the guest entry's slot."""
    base = re.search(r"\bg_ps2RecompiledFunctionTableBase = (0x[0-9a-f]+)u;", source)
    constructor = re.search(
        r"^    GeneratedFunctionTableInitializer\(\) \{\n(.*?)^    \}\s*\n\};\n"
        r"static const GeneratedFunctionTableInitializer g_generatedFunctionTableInitializer;",
        source, re.M | re.S)
    if not base or not constructor or not constructor[1].strip():
        raise ValueError(f"{path}: empty or placeholder generated function registrar")

    base = int(base[1], 16)
    end = re.search(r"\bg_ps2RecompiledFunctionTableEnd = (0x[0-9a-f]+)u;", source)
    count = re.search(r"\bg_ps2RecompiledFunctionTableSlotCount = (\d+)u;", source)
    array = re.search(r"\bg_ps2RecompiledFunctionTable\[(\d+)u\] = \{\};", source)
    if (not end or not count or not array or base % 4
            or int(end[1], 16) - base != int(count[1]) * 4 or count[1] != array[1]):
        raise ValueError(f"{path}: inconsistent generated function table bounds")

    slots = set()
    for line in constructor[1].splitlines():
        row = re.fullmatch(
            r"\s*g_ps2RecompiledFunctionTable\[(\d+)u?\] = ([A-Za-z_]\w*); // (0x[0-9a-f]+)", line)
        if not row:
            raise ValueError(f"{path}: malformed generated function table assignment: {line.strip()}")
        slot, name, address = int(row[1]), row[2], int(row[3], 16)
        if (slot in slots or slot >= int(count[1]) or address != base + 4 * slot
                or name in {"nullptr", "NULL", "false", "true"}):
            raise ValueError(f"{path}: invalid or duplicate generated function table slot {slot} ({address:#x})")
        slots.add(slot)

    slot, offset = divmod(entry - base, 4)
    if offset or slot not in slots:
        raise ValueError(f"{path}: guest ELF entry {entry:#x} has no generated function mapping")
    return base, slot


def entry_symbol(entry):
    return f"xs_generated_entry_{entry:08x}"


def require_export(exe, entry, exports):
    if entry_symbol(entry) not in exports:
        raise ValueError(f"{exe}: missing generated registrar export for guest ELF entry {entry:#x}; "
                         "run assemble.py and rebuild ps2EntryRunner before staging")


def verify_pe(exe, elf, objdump="objdump"):
    listing = subprocess.check_output([objdump, "-p", str(exe)], text=True, stderr=subprocess.STDOUT)
    # Recent GNU objdump adds an ordinal-base and hint column.
    exports = re.findall(
        r"^[ \t]*\[[ \t]*\d+\][ \t]+(?:\+base\[[ \t]*\d+\][ \t]+[0-9a-fA-F]+[ \t]+)?"
        r"(xs_generated_entry_[0-9a-f]{8})[ \t]*$", listing, re.M)
    require_export(exe, elf_entry(elf), exports)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check the linked Windows registrar before installation.")
    parser.add_argument("exe", type=Path)
    parser.add_argument("elf", type=Path)
    args = parser.parse_args()
    try:
        verify_pe(args.exe, args.elf)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Registrar preflight failed: {error}\n")
