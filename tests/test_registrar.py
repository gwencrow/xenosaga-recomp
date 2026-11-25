"""Run from the port checkout with python3 -m unittest discover -s tests."""

import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from registrar import elf_entry, entry_slot, require_export


REGISTRAR = """extern const uint32_t g_ps2RecompiledFunctionTableBase = 0x1000u;
extern const uint32_t g_ps2RecompiledFunctionTableEnd = 0x100cu;
extern const uint32_t g_ps2RecompiledFunctionTableSlotCount = 3u;
PS2Runtime::RecompiledFunction g_ps2RecompiledFunctionTable[3u] = {};
namespace {
struct GeneratedFunctionTableInitializer {
    GeneratedFunctionTableInitializer() {
        g_ps2RecompiledFunctionTable[0] = first; // 0x1000
        g_ps2RecompiledFunctionTable[2] = start; // 0x1008
    }
};
static const GeneratedFunctionTableInitializer g_generatedFunctionTableInitializer;
}
"""
ENTRY_ROW = "        g_ps2RecompiledFunctionTable[2] = start; // 0x1008\n"


def elf_header(entry):
    header = bytearray(52)
    header[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHII", header, 16, 2, 8, 1, entry)
    return header


class RegistrarTests(unittest.TestCase):
    def test_elf_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guest.elf"
            path.write_bytes(elf_header(0x1008))
            self.assertEqual(elf_entry(path), 0x1008)
            path.write_bytes(elf_header(0x1009))
            with self.assertRaisesRegex(ValueError, "invalid guest ELF entry"):
                elf_entry(path)
            path.write_bytes(b"\x7fELF")
            with self.assertRaisesRegex(ValueError, "expected a little-endian ELF32"):
                elf_entry(path)

    def test_nonzero_entry_slot_with_sparse_table(self):
        self.assertEqual(entry_slot(REGISTRAR, 0x1008, "fixture"), (0x1000, 2))

    def test_placeholder_and_empty_constructor(self):
        empty_constructor = REGISTRAR.replace(ENTRY_ROW, "").replace(
            "        g_ps2RecompiledFunctionTable[0] = first; // 0x1000\n", "")
        for source in ("", REGISTRAR.split("namespace")[0], empty_constructor):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "empty or placeholder"):
                    entry_slot(source, 0x1008, "fixture")

    def test_missing_entry_or_entry_only_in_comment(self):
        for source in (REGISTRAR.replace(ENTRY_ROW, ""), REGISTRAR):
            entry = 0x1008 if source != REGISTRAR else 0x1004
            with self.subTest(entry=entry):
                with self.assertRaisesRegex(ValueError, "has no generated function mapping"):
                    entry_slot(source + "// " + ENTRY_ROW, entry, "fixture")

    def test_reject_invalid_assignments_and_bounds(self):
        cases = (
            (REGISTRAR.replace("[3u]", "[2u]"), "inconsistent"),
            (REGISTRAR.replace("[2]", "[3]"), "invalid or duplicate"),
            (REGISTRAR.replace("0x1008", "0x1004"), "invalid or duplicate"),
            (REGISTRAR.replace("= start", "= nullptr"), "invalid or duplicate"),
            (REGISTRAR.replace(ENTRY_ROW, ENTRY_ROW * 2), "invalid or duplicate"),
        )
        for source, error in cases:
            with self.subTest(error=error):
                with self.assertRaisesRegex(ValueError, error):
                    entry_slot(source, 0x1008, "fixture")

    def test_linked_entry_identity(self):
        require_export("game.exe", 0x1008, {"xs_generated_entry_00001008"})
        for exports in (set(), {"xs_generated_entry_00001000"}):
            with self.subTest(exports=exports):
                with self.assertRaisesRegex(ValueError, "guest ELF entry 0x1008"):
                    require_export("game.exe", 0x1008, exports)

    def test_assembly_reports_missing_registrar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            elf = root / "guest.elf"
            elf.write_bytes(elf_header(0x1008))
            result = subprocess.run(
                [sys.executable, str(TOOLS / "assemble.py"), "--elf", str(elf)],
                env=dict(os.environ, XS_ROOT=tmp, XS_PORT=str(TOOLS.parent),
                         PS2RECOMP=str(root / "upstream")),
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("@@ERROR Registrar preflight failed", result.stderr)
            self.assertIn("register_functions.cpp", result.stderr)
            self.assertIn("setup_recomp.py", result.stderr)


if __name__ == "__main__":
    unittest.main()
