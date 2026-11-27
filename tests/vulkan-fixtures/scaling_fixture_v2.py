"""Deterministic GS scaling fixture v2: generator and analytic comparator.

  scaling_fixture_v2.py generate OUT_DIR
  scaling_fixture_v2.py compare FIXTURE NATIVE_RUN RUN SAMPLES GRID [--json OUT] [--png-dir DIR] [--ss-textures]
  scaling_fixture_v2.py analytic-png FIXTURE SAMPLES GRID OUT.png

An earlier fixture version established, by execution, that the pinned paraLLEl-GS
rasterizes sprites and flat-Z "UI-like" triangles at native sample positions
even when super-sampling (gs_interface.cpp STATE_BIT_SNAP_*,
triangle_setup.comp, single_sample_heuristic.comp), and that native VRAM holds
the box resolve of the samples. v2 therefore:

  * draws all discriminating geometry as genuine 3D triangles (per-vertex Z),
    which upstream super-samples;
  * keeps three explicit UI-demotion probes (sub-pixel sprite, minified
    textured sprite, flat-Z triangle) whose expected result is native
    rasterization replicated to every sample;
  * models native VRAM at scale > 1 as the mean of the pixel's samples.

The analytic reference uses exact rational arithmetic on the GS 1/16 pixel
grid at the upstream sample positions. Samples on an edge, at a depth tie
(or within 64 Z units of a crossing) or on a texel boundary are ambiguous and
excluded from exact comparison.
"""
from fractions import Fraction as F
from pathlib import Path
import json
import struct
import sys
import zlib

W = H = 64
SCENE_FBP, FEEDBACK_FBP, TEX_PAGE, ZBP = 0, 4, 8, 10
TEX_W = TEX_H = 32
BG = (16, 16, 48, 0x80)

REG = dict(PRIM=0x00, RGBAQ=0x01, UV=0x03, XYZ2=0x05, TEX0_1=0x06, CLAMP_1=0x08, TEX1_1=0x14,
           XYOFFSET_1=0x18, PRMODECONT=0x1A, TEXFLUSH=0x3F, SCISSOR_1=0x40, ALPHA_1=0x42,
           DTHE=0x45, COLCLAMP=0x46, TEST_1=0x47, PABE=0x49, FBA_1=0x4A, FRAME_1=0x4C,
           ZBUF_1=0x4E, BITBLTBUF=0x50, TRXPOS=0x51, TRXREG=0x52, TRXDIR=0x53, FINISH=0x61)
PRIM_TRI, PRIM_SPRITE = 3, 6
TME, ABE, FST = 1 << 4, 1 << 6, 1 << 8
Z_ALWAYS, Z_GEQUAL = 0x30000, 0x50000


def tag(loops, fmt, regs=0xE, nreg=1, eop=True):
    return struct.pack("<QQ", loops | (int(eop) << 15) | (fmt << 58) | (nreg << 60), regs)


def ad(*writes):
    return tag(len(writes), 0) + b"".join(struct.pack("<QQ", val, addr) for addr, val in writes)


def fx(v):
    q = F(v) * 16
    assert q.denominator == 1, v
    return int(q)


def xyz(x, y, z):
    return fx(x) | (fx(y) << 16) | (z << 32)


def rgbaq(c):
    r, g, b, a = c
    return r | (g << 8) | (b << 16) | (a << 24) | (0x3F800000 << 32)


def uvreg(u, v):
    return fx(u) | (fx(v) << 16)


def frame(fbp):
    return fbp | (1 << 16)


def zbuf(mask):
    return ZBP | (int(mask) << 32)


def tex0(page, log2w, log2h):
    return page * 32 | (1 << 14) | (log2w << 26) | (log2h << 30) | (1 << 34) | (1 << 35)


def texel(u, v):
    return ((u * 8) & 0xFF, (v * 8) & 0xFF, 255 if (u ^ v) & 1 else 0, 0x80)


def P(n):
    """Sixteenths to pixels."""
    return F(n, 16)

# ------------------------------------------------------------------ scene
# Each primitive: dict(name, kind=tri|sprite, verts=[(x,y,z[,u,v])...], color, blend, tex, snap)
# snap=True means upstream rasterizes and interpolates at the native sample point.

def quad_tris(x0, y0, x1, y1, z00, z10, z01, z11, uv=None):
    """Two triangles covering [x0,x1]x[y0,y1] with per-corner Z (and optional per-corner UV)."""
    def v(x, y, z, cu, cv):
        return (x, y, z) + ((cu, cv) if uv else ())
    if uv:
        (u0, v0), (u1, v1) = uv
    else:
        u0 = v0 = u1 = v1 = None
    a = v(x0, y0, z00, u0, v0)
    b = v(x1, y0, z10, u1, v0)
    c = v(x0, y1, z01, u0, v1)
    d = v(x1, y1, z11, u1, v1)
    return [a, b, c], [b, d, c]


TEXQ = quad_tris(F(44), F(4), F(60), F(20), 0xE800, 0xE880, 0xE880, 0xE900,
                 uv=((F(1, 4), F(1, 4)), (F(129, 4), F(129, 4))))
SUBQ = quad_tris(P(646), P(388), P(654), P(644), 0xE200, 0xE240, 0xE280, 0xE2C0)

PRIMS = [
    dict(name="clear", kind="sprite", verts=[(F(0), F(0), 0), (F(W), F(H), 0)], color=BG, ztest=Z_ALWAYS, snap=True),
    dict(name="tri-a-red-3d", kind="tri", verts=[(P(53), P(83), 0x7F00), (P(939), P(151), 0x8000), (P(201), P(973), 0x8100)],
         color=(220, 40, 40, 0x80)),
    dict(name="tri-b-green-depth-3d", kind="tri", verts=[(P(483), P(41), 0x3000), (P(983), P(805), 0xD000), (P(109), P(655), 0x9000)],
         color=(40, 200, 60, 0x80)),
    dict(name="tri-c-white-sliver-3d", kind="tri", verts=[(P(163), P(767), 0xE000), (P(857), P(933), 0xE080), (P(857), P(941), 0xE100)],
         color=(250, 250, 250, 0x80)),
    dict(name="quad-yellow-subpixel-3d-0", kind="tri", verts=SUBQ[0], color=(250, 220, 30, 0x80)),
    dict(name="quad-yellow-subpixel-3d-1", kind="tri", verts=SUBQ[1], color=(250, 220, 30, 0x80)),
    dict(name="quad-textured-minified-3d-0", kind="tri", verts=TEXQ[0], color=(128, 128, 128, 0x80), tex=True),
    dict(name="quad-textured-minified-3d-1", kind="tri", verts=TEXQ[1], color=(128, 128, 128, 0x80), tex=True),
    dict(name="tri-d-blue-alpha-3d", kind="tri", verts=[(P(546), P(481), 0xF000), (P(1005), P(543), 0xF080), (P(735), P(999), 0xF100)],
         color=(40, 80, 255, 0x40), blend=True),
    # UI-demotion probes: expected to rasterize at native sample positions at every scale.
    dict(name="probe-sprite-orange-subpixel", kind="sprite", verts=[(P(326), P(68), 0xF800), (P(334), P(324), 0xF800)],
         color=(250, 140, 20, 0x80), snap=True, probe=True),
    dict(name="probe-sprite-textured-minified", kind="sprite",
         verts=[(F(2), F(44), 0xF800, F(1, 4), F(1, 4)), (F(18), F(60), 0xF800, F(129, 4), F(129, 4))],
         color=(128, 128, 128, 0x80), tex=True, snap=True, probe=True),
    dict(name="probe-tri-cyan-flat-z", kind="tri", verts=[(P(37), P(5), 0xF900), (P(299), P(21), 0xF900), (P(91), P(291), 0xF900)],
         color=(30, 220, 230, 0x80), snap=True, probe=True),
]
FEEDBACK = ((F(0), F(0)), (F(W), F(H)), (F(1, 16), F(1, 16)), (F(W) + F(1, 16), F(H) + F(1, 16)))


def prim_packet(p):
    prim = PRIM_TRI if p["kind"] == "tri" else PRIM_SPRITE
    if p.get("blend"):
        prim |= ABE
    w = [(REG["TEST_1"], p.get("ztest", Z_GEQUAL))]
    if p.get("tex"):
        w.append((REG["TEX0_1"], tex0(TEX_PAGE, 5, 5)))
        prim |= TME | FST
    w += [(REG["PRIM"], prim), (REG["RGBAQ"], rgbaq(p["color"]))]
    for v in p["verts"]:
        if p.get("tex"):
            w.append((REG["UV"], uvreg(v[3], v[4])))
        w.append((REG["XYZ2"], xyz(v[0], v[1], v[2])))
    return ad(*w)


def build_ops():
    setup = ad((REG["XYOFFSET_1"], 0), (REG["SCISSOR_1"], (63 << 16) | (63 << 48)),
               (REG["PRMODECONT"], 1), (REG["FRAME_1"], frame(SCENE_FBP)), (REG["ZBUF_1"], zbuf(False)),
               (REG["TEST_1"], Z_ALWAYS), (REG["ALPHA_1"], 0x44), (REG["COLCLAMP"], 1), (REG["DTHE"], 0),
               (REG["PABE"], 0), (REG["FBA_1"], 0), (REG["TEX1_1"], 1), (REG["CLAMP_1"], 0x5))
    tex_raw = b"".join(struct.pack("<4B", *texel(u, v)) for v in range(TEX_H) for u in range(TEX_W))
    upload_setup = ad((REG["BITBLTBUF"], (TEX_PAGE * 32 | (1 << 16)) << 32), (REG["TRXPOS"], 0),
                      (REG["TRXREG"], TEX_W | (TEX_H << 32)), (REG["TRXDIR"], 0))
    image = tag(len(tex_raw) // 16, 2, regs=0) + tex_raw
    (fx0, fy0), (fx1, fy1), (fu0, fv0), (fu1, fv1) = FEEDBACK
    feedback = ad((REG["FRAME_1"], frame(FEEDBACK_FBP)), (REG["ZBUF_1"], zbuf(True)), (REG["TEST_1"], Z_ALWAYS),
                  (REG["TEX0_1"], tex0(SCENE_FBP, 6, 6)), (REG["PRIM"], PRIM_SPRITE | TME | FST),
                  (REG["RGBAQ"], rgbaq((128, 128, 128, 0x80))),
                  (REG["UV"], uvreg(fu0, fv0)), (REG["XYZ2"], xyz(fx0, fy0, 0)),
                  (REG["UV"], uvreg(fu1, fv1)), (REG["XYZ2"], xyz(fx1, fy1, 0)))
    readback = ad((REG["BITBLTBUF"], SCENE_FBP * 32 | (1 << 16)), (REG["TRXPOS"], 0),
                  (REG["TRXREG"], W | (H << 32)), (REG["TRXDIR"], 1))
    display = (1 << 23) | ((W * 2 - 1) << 32) | ((H - 1) << 44)
    ops = [("gif", "setup", setup), ("gif", "texture-upload-setup", upload_setup),
           ("gif", "texture-image", image), ("gif", "texflush-0", ad((REG["TEXFLUSH"], 0))),
           ("vram", "after-texture-upload", None)]
    ops += [("gif", p["name"], prim_packet(p)) for p in PRIMS]
    ops += [("gif", "finish-scene", ad((REG["FINISH"], 0))), ("vram", "after-scene", None),
            ("gif", "texflush-1", ad((REG["TEXFLUSH"], 0))), ("gif", "feedback-copy", feedback),
            ("gif", "finish-feedback", ad((REG["FINISH"], 0))), ("vram", "after-feedback", None),
            ("gif", "local-to-host-setup", readback), ("fifo", "scene-fifo", W * H * 4 // 16),
            ("scanout", "scene-scanout", (SCENE_FBP | (1 << 9), display)),
            ("scanout", "feedback-scanout", (FEEDBACK_FBP | (1 << 9), display))]
    return ops, tex_raw


def generate(out):
    out.mkdir(exist_ok=False)
    ops, tex_raw = build_ops()
    commands = []
    for i, (kind, name, data) in enumerate(ops):
        if kind == "gif":
            fname = f"{i:02}-{name}.bin"
            (out / fname).write_bytes(data)
            commands.append(f"gif 2 {fname}")
        elif kind == "vram":
            commands.append(f"vram {name}.vram")
        elif kind == "fifo":
            commands.append(f"fifo {data} {name}.rgba")
        else:
            dispfb, display = data
            commands.append(f"scanout 0 ff21 78 0 {dispfb:x} {display:x} 0 {name}.rgba")
    (out / "commands.txt").write_text("\n".join(commands) + "\n")
    (out / "texture.rgba").write_bytes(tex_raw)
    (out / "fixture.json").write_text(json.dumps({
        "version": 2, "canvas": [W, H], "scene_fbp": SCENE_FBP, "feedback_fbp": FEEDBACK_FBP,
        "texture_page": TEX_PAGE, "zbp": ZBP,
        "primitives": [{"name": p["name"], "kind": p["kind"], "snap_expected": bool(p.get("snap")),
                        "probe": bool(p.get("probe"))} for p in PRIMS],
        "finish_ordinals": [i for i, c in enumerate(commands) if "finish-" in c],
    }, indent=2) + "\n")

# ------------------------------------------------------------------ swizzle

BLOCK32 = [[0, 1, 4, 5, 16, 17, 20, 21], [2, 3, 6, 7, 18, 19, 22, 23],
           [8, 9, 12, 13, 24, 25, 28, 29], [10, 11, 14, 15, 26, 27, 30, 31]]


def ct32_addr(fbp, fbw, x, y):
    page = fbp + (y // 32) * fbw + x // 64
    px, py = x % 64, y % 32
    return page * 8192 + BLOCK32[py // 8][px // 8] * 256 + ((py % 8) // 2) * 64 + \
        (((px % 8) // 2) * 4 + (py % 2) * 2 + px % 2) * 4


def decode(vram, fbp, w=W, h=H):
    out = bytearray()
    for y in range(h):
        for x in range(w):
            a = ct32_addr(fbp, 1, x, y)
            out += vram[a:a + 4]
    return bytes(out)

# ------------------------------------------------------------------ analytic model

def sample_points(samples, ordered):
    if samples == 1:
        return [(F(0), F(0))], 0, 0
    rx, ry = {2: (0, 1), 4: (1, 1) if ordered else (0, 2), 8: (1, 2),
              16: (2, 2) if ordered else (1, 3)}[samples]
    pts = []
    for i in range(samples):
        if ry - rx == 2:
            sparse = (0, 2, 3, 1)
            x, y = (i // 8) * 4 + sparse[i % 4], i % 8
        else:
            y = (i & 1) + ((i >> 2) & 1) * 2
            x = ((i >> 1) & 1) + ((i >> 3) & 1) * 2
            if ry - rx == 1:
                x = x * 2 + i % 2
        pts.append((F(x, 1 << ry), F(y, 1 << ry)))
    return pts, rx, ry


def output_groups(samples, rx, ry, high_res):
    if not high_res or samples < 4 or rx == 0 or ry == 0:
        return 1, {(0, 0): None}
    n = samples // 4
    groups = {}
    for qy in range(2):
        for qx in range(2):
            q = (qx & 1) + (qy & 1) * 2 if samples == 8 else (qy & 1) + (qx & 1) * 2
            groups[(qx, qy)] = list(range(n * q, n * q + n))
    return 2, groups


def edge(a, b, p):
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def bary(verts, p):
    a, b, c = [(v[0], v[1]) for v in verts]
    area = edge(a, b, c)
    return edge(b, c, p) / area, edge(c, a, p) / area, edge(a, b, p) / area


def tri_cover(verts, p):
    a, b, c = [(v[0], v[1]) for v in verts]
    e = [edge(a, b, p), edge(b, c, p), edge(c, a, p)]
    if edge(a, b, c) < 0:
        e = [-x for x in e]
    # A tie only matters on the triangle's boundary (all edge functions >= 0),
    # not on the infinite extension of an edge line.
    if all(x >= 0 for x in e) and any(x == 0 for x in e):
        return False, True
    return all(x > 0 for x in e), False


def sprite_cover(v0, v1, p):
    x0, y0, x1, y1 = v0[0], v0[1], v1[0], v1[1]
    inx = x0 <= p[0] <= x1
    iny = y0 <= p[1] <= y1
    if (p[0] in (x0, x1) and iny) or (p[1] in (y0, y1) and inx):
        return False, True
    return x0 < p[0] < x1 and y0 < p[1] < y1, False


def blend(cs, cd):
    a = cs[3]
    return tuple(max(0, min(255, ((cs[i] - cd[i]) * a >> 7) + cd[i])) for i in range(3)) + (cs[3],)


def shade_sample(p, origin, tex_raw):
    color, z, amb = BG, F(0), False
    for prim in PRIMS:
        q = origin if prim.get("snap") else p
        v = prim["verts"]
        if prim["kind"] == "tri":
            cov, a = tri_cover(v, q)
        else:
            cov, a = sprite_cover(v[0], v[1], q)
        amb |= a
        if not cov:
            continue
        if prim["kind"] == "tri":
            w = bary(v, q)
            zs = sum(w[i] * v[i][2] for i in range(3))
        else:
            zs = F(v[1][2])
        zt = prim.get("ztest", Z_GEQUAL)
        if zt == Z_GEQUAL:
            if zs != z and abs(zs - z) < 64:
                amb = True
            if zs == z and prim["kind"] == "tri" and any(vv[2] != v[0][2] for vv in v):
                amb = True
            if zs < z:
                continue
        col = prim["color"]
        if prim.get("tex"):
            if prim["kind"] == "tri":
                w = bary(v, q)
                u = sum(w[i] * v[i][3] for i in range(3))
                t = sum(w[i] * v[i][4] for i in range(3))
            else:
                u = v[0][3] + (q[0] - v[0][0]) * (v[1][3] - v[0][3]) / (v[1][0] - v[0][0])
                t = v[0][4] + (q[1] - v[0][1]) * (v[1][4] - v[0][4]) / (v[1][1] - v[0][1])
            # Ambiguous within 1/32 texel of a boundary (interpolator precision).
            for c in (u, t):
                fr = c - (c // 1)
                if fr < F(1, 32) or fr > F(31, 32):
                    amb = True
            iu, it = int(u // 1), int(t // 1)
            o = (it * TEX_W + iu) * 4
            col = tuple(tex_raw[o:o + 4])
        if prim.get("blend"):
            col = blend(col, color)
        color, z = col, zs
    return color, amb


def analytic(samples, ordered, tex_raw):
    """Returns per-native-pixel list of (sample colours, ambiguous) plus geometry info."""
    pts, rx, ry = sample_points(samples, ordered)
    pix = []
    for y in range(H):
        for x in range(W):
            origin = (F(x), F(y))
            s = [shade_sample((x + dx, y + dy), origin, tex_raw) for dx, dy in pts]
            pix.append(([c for c, _ in s], [a for _, a in s]))
    return pts, rx, ry, pix


def mean(cols):
    n = len(cols)
    return tuple(sum(c[k] for c in cols) / n for k in range(4))


NATIVE_SCANOUT = False   # set by --native-scanout (VSyncInfo.high_resolution_scanout = false)


def expected_scanout(samples, rx, ry, pix):
    high_res = samples >= 4 and rx > 0 and ry > 0 and not NATIVE_SCANOUT
    scale, groups = output_groups(samples, rx, ry, high_res)
    ow = W * scale
    img, amb = [None] * (ow * H * scale), [False] * (ow * H * scale)
    for y in range(H):
        for x in range(W):
            cols, ambs = pix[y * W + x]
            for (qx, qy), ids in groups.items():
                o = (y * scale + qy) * ow + x * scale + qx
                if ids is None:   # native scanout reads the resolved native value
                    img[o], amb[o] = mean(cols), any(ambs)
                else:
                    img[o], amb[o] = mean([cols[i] for i in ids]), any(ambs[i] for i in ids)
    return scale, img, amb

# ------------------------------------------------------------------ images

def write_png(path, rgba, w, h, zoom=1):
    rows = []
    for y in range(h * zoom):
        row = bytearray([0])
        sy = y // zoom
        for x in range(w * zoom):
            o = (sy * w + x // zoom) * 4
            row += rgba[o:o + 3]
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" +
                           chunk(b"IHDR", struct.pack(">IIBBBBB", w * zoom, h * zoom, 8, 2, 0, 0, 0)) +
                           chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def nearest_upscale(rgba, w, h, s):
    out = bytearray()
    for y in range(h * s):
        for x in range(w * s):
            o = ((y // s) * w + x // s) * 4
            out += rgba[o:o + 4]
    return bytes(out)


def rnd(v):
    return int(v + F(1, 2)) if isinstance(v, F) else int(v + 0.5)


def cmp_img(got, exp, amb, tol):
    bad, maxerr, compared = 0, 0, 0
    for i, e in enumerate(exp):
        if amb[i]:
            continue
        compared += 1
        err = max(abs(got[4 * i + k] - rnd(e[k])) for k in range(4))
        maxerr = max(maxerr, err)
        bad += err > tol
    return bad, maxerr, compared

# ------------------------------------------------------------------ compare

def region_pixels(scale, x0, y0, x1, y1):
    return [(x, y) for y in range(y0 * scale, y1 * scale) for x in range(x0 * scale, x1 * scale)]


def compare(fixture, native_dir, run_dir, samples, grid, json_out=None, png_dir=None, ss_textures=False):
    ordered = grid == "ordered"
    tex_raw = (fixture / "texture.rgba").read_bytes()
    res = {"run": str(run_dir), "samples": samples, "grid": grid, "checks": {}, "metrics": {}}
    c, m = res["checks"], res["metrics"]
    pts, rx, ry, pix = analytic(samples, ordered, tex_raw)
    scale, img, amb = expected_scanout(samples, rx, ry, pix)
    ow, oh = W * scale, H * scale
    m["expected_output"] = f"{ow}x{oh}"

    vram_up = (run_dir / "after-texture-upload.vram").read_bytes()
    vram_scene = (run_dir / "after-scene.vram").read_bytes()
    vram_fb = (run_dir / "after-feedback.vram").read_bytes()
    fifo = (run_dir / "scene-fifo.rgba").read_bytes()
    native_scene = decode(vram_scene, SCENE_FBP)

    # Transfer semantics (exact at every scale).
    c["upload_vram_identical_to_1x"] = vram_up == (native_dir / "after-texture-upload.vram").read_bytes()
    c["texture_bytes_in_vram"] = decode(vram_up, TEX_PAGE, TEX_W, TEX_H) == tex_raw
    c["fifo_equals_native_vram_decode"] = fifo == native_scene
    c["feedback_native_pages_exact_copy"] = vram_fb[FEEDBACK_FBP * 8192:(FEEDBACK_FBP + 2) * 8192] == \
        vram_fb[SCENE_FBP * 8192:(SCENE_FBP + 2) * 8192]
    c["feedback_did_not_modify_scene_pages"] = vram_fb[:2 * 8192] == vram_scene[:2 * 8192]
    other = [(0, SCENE_FBP * 8192), ((SCENE_FBP + 2) * 8192, FEEDBACK_FBP * 8192),
             ((FEEDBACK_FBP + 2) * 8192, TEX_PAGE * 8192), ((TEX_PAGE + 1) * 8192, ZBP * 8192),
             ((ZBP + 2) * 8192, len(vram_fb))]
    c["untouched_vram_zero"] = all(not any(vram_fb[a:b]) for a, b in other)
    for name in ("after-scene.vram", "after-feedback.vram", "scene-fifo.rgba"):
        a, b = (native_dir / name).read_bytes(), (run_dir / name).read_bytes()
        m[f"bytes_differing_from_1x:{name}"] = sum(x != y for x, y in zip(a, b))

    # Native VRAM = resolve (mean) of per-pixel samples.
    nexp = [mean(cols) for cols, _ in pix]
    namb = [any(a) for _, a in pix]
    tol = 0 if samples == 1 else 1
    bad, maxerr, n = cmp_img(native_scene, nexp, namb, tol)
    m["native_vram_vs_analytic_resolve"] = {"mismatches": bad, "max_abs_error": maxerr, "compared": n,
                                            "ambiguous": sum(namb), "tolerance": tol}
    c["native_vram_matches_analytic_resolve"] = bad == 0

    rgba = (run_dir / "scene-scanout.rgba").read_bytes()
    fb = (run_dir / "feedback-scanout.rgba").read_bytes()
    c[f"scene_scanout_dimensions_{ow}x{oh}"] = len(rgba) == ow * oh * 4
    c[f"feedback_scanout_dimensions_{ow}x{oh}"] = len(fb) == ow * oh * 4
    if png_dir:
        for nm, data in (("scene", rgba), ("feedback", fb)):
            if len(data) == ow * oh * 4:
                write_png(png_dir / f"{run_dir.name}-{nm}.png", data, ow, oh, zoom=8 // scale)
    if len(rgba) != ow * oh * 4:
        res["pass"] = False
        return finish(res, json_out)

    stol = 0 if (samples == 1 or (scale == 2 and samples == 4)) else 1
    bad, maxerr, n = cmp_img(rgba, img, amb, stol)
    m["scene_scanout_vs_analytic"] = {"mismatches": bad, "max_abs_error": maxerr, "compared": n,
                                      "ambiguous": sum(amb), "tolerance": stol}
    c["scene_scanout_matches_analytic"] = bad == 0

    native_scan = (native_dir / "scene-scanout.rgba").read_bytes()
    if scale == 1:
        c["scene_scanout_equals_native_vram_decode"] = rgba == native_scene
        if samples == 1:
            c["feedback_scanout_equals_scene_scanout"] = fb == rgba
        else:
            # Native scanout of a super-sampled frame: SSAA used purely as anti-aliasing.
            m["scene_pixels_differing_from_1x_scanout"] = sum(
                rgba[4 * i:4 * i + 4] != native_scan[4 * i:4 * i + 4] for i in range(W * H))
            c["feedback_scanout_equals_native_copy_decode"] = fb == decode(vram_fb, FEEDBACK_FBP)
    else:
        up = nearest_upscale(native_scan, W, H, scale)
        diff = sum(rgba[4 * i:4 * i + 4] != up[4 * i:4 * i + 4] for i in range(ow * oh))
        m["pixels_differing_from_nearest_upscale_of_1x"] = diff
        c["not_a_simple_enlargement_of_1x"] = diff > 0
        if samples == 4:
            dec = b"".join(rgba[((2 * y) * ow + 2 * x) * 4:((2 * y) * ow + 2 * x) * 4 + 4]
                           for y in range(H) for x in range(W))
            c["even_pixels_equal_1x_scanout"] = dec == native_scan

        def count(region, pred, data, s, w):
            return sum(1 for x, y in region_pixels(s, *region) if pred(data[(y * w + x) * 4:(y * w + x) * 4 + 4]))
        yellow = lambda px: tuple(px[:3]) == (250, 220, 30)
        bluechk = lambda px: px[2] == 255
        orange = lambda px: tuple(px[:3]) == (250, 140, 20)
        m["subpixel_3d_quad_pixels"] = [count((38, 22, 44, 42), yellow, native_scan, 1, W),
                                        count((38, 22, 44, 42), yellow, rgba, scale, ow)]
        m["textured_3d_odd_texel_pixels"] = [count((44, 4, 60, 20), bluechk, native_scan, 1, W),
                                             count((44, 4, 60, 20), bluechk, rgba, scale, ow)]
        c["subpixel_3d_detail_absent_1x_present_scaled"] = m["subpixel_3d_quad_pixels"][0] == 0 and m["subpixel_3d_quad_pixels"][1] > 0
        c["texture_3d_detail_absent_1x_present_scaled"] = m["textured_3d_odd_texel_pixels"][0] == 0 and m["textured_3d_odd_texel_pixels"][1] > 0
        # Probes: UI-like primitives must remain native (nearest enlargement in their footprint).
        for nm, reg in (("probe_sprite_textured", (3, 45, 18, 60)),):
            same = all(rgba[(y * ow + x) * 4:(y * ow + x) * 4 + 4] == up[(y * ow + x) * 4:(y * ow + x) * 4 + 4]
                       for x, y in region_pixels(scale, *reg))
            m[f"{nm}_region_equals_nearest_upscale"] = same
        m["probe_sprite_subpixel_pixels"] = [count((19, 3, 23, 22), orange, native_scan, 1, W),
                                             count((19, 3, 23, 22), orange, rgba, scale, ow)]
        c["probe_textured_sprite_stays_native"] = m["probe_sprite_textured_region_equals_nearest_upscale"]
        c["probe_subpixel_sprite_stays_invisible"] = m["probe_sprite_subpixel_pixels"] == [0, 0]
        # Feedback via a sprite blit: upstream samples the resolved native texels (UI path).
        fb_up = nearest_upscale(decode(vram_fb, FEEDBACK_FBP), W, H, scale)
        m["feedback_scanout_equals_nearest_upscale_of_native_copy"] = fb == fb_up
        m["feedback_scanout_equals_direct_scene_scanout"] = fb == rgba
        m["feedback_pixels_differing_from_direct"] = sum(fb[4*i:4*i+4] != rgba[4*i:4*i+4] for i in range(ow * oh))
        if not ss_textures:
            c["feedback_scanout_is_native_resolution_blit"] = fb == fb_up
    res["pass"] = all(c.values())
    return finish(res, json_out)


def finish(res, json_out):
    if json_out:
        Path(json_out).write_text(json.dumps(res, indent=2) + "\n")
    for k, v in res["checks"].items():
        print(f"check {k}: {'PASS' if v else 'FAIL'}")
    for k, v in res["metrics"].items():
        print(f"metric {k}: {v}")
    print("OVERALL:", "PASS" if res["pass"] else "FAIL")
    return res["pass"]


def main():
    a = sys.argv[1:]
    if a[:1] == ["generate"] and len(a) == 2:
        generate(Path(a[1]))
        return 0
    if a[:1] == ["analytic-png"] and len(a) == 5:
        tex_raw = (Path(a[1]) / "texture.rgba").read_bytes()
        s = int(a[2])
        pts, rx, ry, pix = analytic(s, a[3] == "ordered", tex_raw)
        scale, img, amb = expected_scanout(s, rx, ry, pix)
        buf = bytearray()
        for i in range(len(img)):
            buf += bytes((255, 0, 255, 255)) if amb[i] else bytes(rnd(v) for v in img[i])
        write_png(a[4], buf, W * scale, H * scale, zoom=8 // scale)
        return 0
    if a[:1] == ["resolve-rule"] and len(a) == 5:
        # resolve-rule FIXTURE RUN SAMPLES GRID: which rounding maps the sample mean to native VRAM.
        tex_raw = (Path(a[1]) / "texture.rgba").read_bytes()
        pts, rx, ry, pix = analytic(int(a[3]), a[4] == "ordered", tex_raw)
        native = decode((Path(a[2]) / "after-scene.vram").read_bytes(), SCENE_FBP)
        rules = {"floor": lambda v: int(v // 1), "round_half_up": lambda v: int((v + F(1, 2)) // 1),
                 "round_half_even": lambda v: round(v), "ceil": lambda v: -int((-v) // 1)}
        hits = {k: 0 for k in rules}
        n = 0
        for i, (cols, ambs) in enumerate(pix):
            if any(ambs):
                continue
            for k in range(4):
                v = F(sum(c[k] for c in cols), len(cols))
                if v.denominator == 1:
                    continue
                n += 1
                for name, fn in rules.items():
                    hits[name] += fn(v) == native[4 * i + k]
        print(json.dumps({"non_integer_channel_means": n, "matches": hits}))
        return 0
    if a[:1] == ["compare"] and len(a) >= 6:
        json_out = png_dir = None
        ss = False
        rest = a[6:]
        global NATIVE_SCANOUT
        while rest:
            if rest[0] in ("--ss-textures", "--native-scanout"):
                if rest[0] == "--ss-textures":
                    ss = True
                else:
                    NATIVE_SCANOUT = True
                rest = rest[1:]
                continue
            if rest[0] == "--json":
                json_out = rest[1]
            elif rest[0] == "--png-dir":
                png_dir = Path(rest[1])
            rest = rest[2:]
        return 0 if compare(Path(a[1]), Path(a[2]), Path(a[3]), int(a[4]), a[5], json_out, png_dir, ss) else 1
    raise SystemExit(__doc__)


sys.exit(main())
