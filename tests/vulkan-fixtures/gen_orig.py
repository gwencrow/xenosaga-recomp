"""Generate the deterministic "orig" GS fixture: PSMCT32 upload, draw, alias sample and readback.

All data is synthetic (a computed 16x16 gradient); nothing is derived from game data.
Usage: gen_orig.py OUT_DIR
"""
from pathlib import Path
import csv
import json
import struct
import sys

WIDTH = HEIGHT = 16
VRAM_BYTES = 4 * 1024 * 1024
# GS FRAME bases use pages (8192 bytes), TEX0/BITBLTBUF bases use 256-byte blocks.
TEXTURE_PAGE, SOURCE_PAGE, RESULT_PAGE = 0, 1, 2
PIXELS = [
    0x80000000 | ((x * 17) << 16) | ((y * 17) << 8) | ((x ^ y) * 17)
    for y in range(HEIGHT) for x in range(WIDTH)
]
# The four 8x8 CT32 blocks of the fixture within a GS page.
BLOCKS = ((0, 1), (2, 3))


def tag(loops, fmt, regs=0xE, nreg=1, eop=True):
    return struct.pack("<QQ", loops | (int(eop) << 15) | (fmt << 58) | (nreg << 60), regs)


def ad(*writes):
    return tag(len(writes), 0) + b"".join(struct.pack("<QQ", val, addr) for addr, val in writes)


def texture(page):
    # PSMCT32, TBW=1, TW=TH=4, TCC=RGBA, TFX=DECAL.
    return page * 32 | (1 << 14) | (4 << 26) | (4 << 30) | (1 << 34) | (1 << 35)


def frame(page):
    return page | (1 << 16)


def draw(texture_page, frame_page):
    # Sprite, fixed UV, nearest sampling, no blending or alpha test, depth compare always and writes masked.
    return ad((0x4C, frame(frame_page)), (0x06, texture(texture_page)), (0x14, 0),
              (0x00, 6 | (1 << 4) | (1 << 8)), (0x01, 0x3F80000080808080),
              (0x03, 0), (0x05, 0), (0x03, (HEIGHT * 16 << 16) | (WIDTH * 16)),
              (0x05, (HEIGHT * 16 << 16) | (WIDTH * 16)))


def ct32_offset(page, x, y):
    # Each 8x8 block is four two-row columns. Column words interleave x
    # pairs and y parity: row 0 starts at words 0/1 and row 1 at 2/3.
    block = BLOCKS[y // 8][x // 8]
    column = (y % 8) // 2
    lane = ((x % 8) // 2) * 4 + (y % 2) * 2 + x % 2
    return page * 8192 + block * 256 + column * 64 + lane * 4


def expected_vram(pages):
    expected = bytearray(VRAM_BYTES)
    for page in pages:
        for i, pixel in enumerate(PIXELS):
            struct.pack_into("<I", expected, ct32_offset(page, i % WIDTH, i // WIDTH), pixel)
    return expected


out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "fixture"
out.mkdir(exist_ok=False)
raw = b"".join(struct.pack("<I", p) for p in PIXELS)
setup = ad((0x18, 0), (0x40, (63 << 16) | (31 << 48)),
           (0x4E, 0x1000001FF), (0x47, 0x30000), (0x1A, 1),
           (0x50, 1 << 48), (0x51, 0), (0x52, WIDTH | (HEIGHT << 32)), (0x53, 0))
ops = [
    ("gif", "upload-setup", setup),
    ("gif", "image", tag(len(raw) // 16, 2, regs=0) + raw),
    ("gif", "texture-state", ad((0x3F, 0))),
    ("checkpoint", "after-upload", b""),
    ("gif", "draw-texture-into-framebuffer", draw(TEXTURE_PAGE, SOURCE_PAGE)),
    ("gif", "finish-source", ad((0x61, 0))),
    ("checkpoint", "after-source", b""),
    ("gif", "flush-source-texture-cache", ad((0x3F, 0))),
    ("gif", "reuse-framebuffer-as-texture", draw(SOURCE_PAGE, RESULT_PAGE)),
    ("gif", "finish-result", ad((0x61, 0))),
    ("checkpoint", "after-result", b""),
    ("gif", "local-to-host-setup", ad((0x50, RESULT_PAGE * 32 | (1 << 16)),
                                     (0x51, 0), (0x52, WIDTH | (HEIGHT << 32)), (0x53, 1))),
    ("fifo", "read-result", b""),
    ("scanout", "ct32-result-phase0", b""),
]
scanout = {
    "phase": 0, "pmode": "0xff21", "smode1": "0x78", "smode2": "0x0",
    "dispfb1": hex(RESULT_PAGE | (1 << 9)),
    "display1": hex((1 << 23) | ((WIDTH * 2 - 1) << 32) | ((HEIGHT - 1) << 44)), "bgcolor": "0x0",
    "crop": [0, 0, WIDTH, HEIGHT],
}
commands = []
with (out / "events.csv").open("w", newline="") as manifest:
    writer = csv.writer(manifest)
    writer.writerow(("ordinal", "operation", "name", "gif-path-index", "payload", "bytes"))
    for index, (kind, name, data) in enumerate(ops):
        payload = ""
        if kind == "gif":
            payload = f"{index:02}-{name}.bin"
            (out / payload).write_bytes(data)
            commands.append(f"gif 2 {payload}")
        elif kind == "checkpoint":
            commands.append(f"vram {name}.vram")
        if kind == "fifo":
            payload = "fifo.json"
            (out / payload).write_text(json.dumps({"qwords": len(raw) // 16}, indent=2) + "\n")
            commands.append(f"fifo {len(raw) // 16} result-fifo.rgba")
        elif kind == "scanout":
            payload = "scanout.json"
            (out / payload).write_text(json.dumps(scanout, indent=2) + "\n")
            registers = " ".join(scanout[k].removeprefix("0x") for k in
                                 ("pmode", "smode1", "smode2", "dispfb1", "display1", "bgcolor"))
            commands.append(f"scanout {scanout['phase']} {registers} result-scanout.rgba")
        writer.writerow((index, kind, name, 2 if kind == "gif" else "", payload, len(data)))
(out / "commands.txt").write_text("\n".join(commands) + "\n")
(out / "expected-fifo.rgba").write_bytes(raw)
(out / "expected-native-region.ppm").write_bytes(
    f"P6\n{WIDTH} {HEIGHT}\n255\n".encode() + b"".join(raw[i:i+3] for i in range(0, len(raw), 4)))
for name, pages in (("upload", [0]), ("source", [0, 1]), ("result", [0, 1, 2])):
    (out / f"expected-{name}.vram").write_bytes(expected_vram(pages))
