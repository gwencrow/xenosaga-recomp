"""Derive the split-IMAGE fixture from the orig fixture.

The IMAGE transfer (01-image.bin: GIF tag + 1024 bytes of pixels) is cut at a 16-byte payload boundary
in the middle of its payload and sent as two GIF packets on the same path. Every other command and
payload is copied unchanged. A correct GS gives a result identical to the unsplit fixture.

Usage: gen_split.py ORIG_DIR OUT_DIR
"""
from pathlib import Path
import shutil
import sys

IMAGE_LINE = "gif 2 01-image.bin"
SPLIT_LINES = ["gif 2 image-head.bin", "gif 2 image-tail.bin"]

orig, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(exist_ok=False)
commands = (orig / "commands.txt").read_text().splitlines()
position = commands.index(IMAGE_LINE)
for line in commands:
    if line.startswith("gif ") and line != IMAGE_LINE:
        name = line.split()[2]
        shutil.copyfile(orig / name, out / name)
image = (orig / "01-image.bin").read_bytes()
cut = 16 + (len(image) - 16) // 2
if cut % 16 or cut <= 16 or cut >= len(image):
    raise SystemExit("Cannot split IMAGE at a 16-byte payload boundary")
(out / "image-head.bin").write_bytes(image[:cut])
(out / "image-tail.bin").write_bytes(image[cut:])
commands[position:position + 1] = SPLIT_LINES
(out / "commands.txt").write_text("\n".join(commands) + "\n")
