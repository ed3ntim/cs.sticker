# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Generate the embedded demo sticker set (one sticker per finish) and its
catalog.json. Original artwork drawn from signed distance functions, so the
add-on ships no third-party game assets.

Pure Python (zlib only). Run with any Python 3.9+:
    python tools/generate_demo_textures.py
"""

import json
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "cs_sticker", "stickers", "core")
TEX_DIR = os.path.join(OUT_DIR, "textures")
SIZE = 256
COLLECTION = "Demo Capsule"


# ---------------------------------------------------------------------------
# PNG writer
# ---------------------------------------------------------------------------

def write_png(path, width, height, pixels, channels=4):
    """pixels: flat list of 0..1 floats, row-major, top row first."""
    color_type = {1: 0, 3: 2, 4: 6}[channels]
    raw = bytearray()
    stride = width * channels
    for y in range(height):
        raw.append(0)
        row = pixels[y * stride:(y + 1) * stride]
        raw.extend(max(0, min(255, int(round(v * 255)))) for v in row)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


# ---------------------------------------------------------------------------
# Signed distance helpers (coordinates in -1..1, y up)
# ---------------------------------------------------------------------------

def sd_circle(x, y, r):
    return math.hypot(x, y) - r


def sd_polygon(x, y, pts):
    d = float("inf")
    inside = False
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        wx, wy = x - ax, y - ay
        t = max(0.0, min(1.0, (wx * ex + wy * ey) / (ex * ex + ey * ey)))
        d = min(d, math.hypot(wx - ex * t, wy - ey * t))
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return -d if inside else d


def star(n, r_out, r_in, rot=math.pi / 2):
    pts = []
    for i in range(n * 2):
        a = rot + i * math.pi / n
        r = r_out if i % 2 == 0 else r_in
        pts.append((math.cos(a) * r, math.sin(a) * r))
    return pts


def heart(scale=0.055, steps=90):
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x * scale, y * scale + 0.05))
    return pts


def ellipse(rx, ry, steps=72):
    return [(math.cos(2 * math.pi * i / steps) * rx, math.sin(2 * math.pi * i / steps) * ry)
            for i in range(steps)]


def regular(n, r, rot=0.0):
    return [(math.cos(rot + 2 * math.pi * i / n) * r, math.sin(rot + 2 * math.pi * i / n) * r)
            for i in range(n)]


SHIELD = [(-0.7, 0.75), (0.7, 0.75), (0.68, 0.0), (0.0, -0.85), (-0.68, 0.0)]
CROWN = [(-0.8, -0.5), (0.8, -0.5), (0.85, 0.45), (0.45, 0.05), (0.0, 0.65),
         (-0.45, 0.05), (-0.85, 0.45)]


def cover(d, px=2.0 / SIZE):
    """Anti-aliased coverage from a signed distance."""
    return max(0.0, min(1.0, 0.5 - d / px))


def smooth(e0, e1, v):
    t = max(0.0, min(1.0, (v - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(width, height, shade):
    """shade(u, v, x, y) -> tuple of channel floats; x/y in -1..1 per frame."""
    out = []
    for j in range(height):
        for i in range(width):
            u = (i + 0.5) / width
            v = 1.0 - (j + 0.5) / height
            x = ((i + 0.5) / height) * 2 - 1  # square frames side by side
            y = v * 2 - 1
            out.extend(shade(u, v, x, y))
    return out


def normal_from_height(width, height, h, strength=4.0):
    """Tangent-space normal map (OpenGL convention, +Y up) from a height list."""
    out = []
    for j in range(height):
        for i in range(width):
            hl = h[j * width + max(i - 1, 0)]
            hr = h[j * width + min(i + 1, width - 1)]
            hu = h[max(j - 1, 0) * width + i]
            hd = h[min(j + 1, height - 1) * width + i]
            dx = (hr - hl) * strength
            dy = (hu - hd) * strength  # image rows go down, +Y goes up
            nx, ny, nz = -dx, -dy, 1.0
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            out.extend((nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, nz / ln * 0.5 + 0.5))
    return out


def sticker_shape(d_shape, border=0.06):
    """Alpha (shape + white die-cut border) and border mask."""
    a = cover(d_shape - border)
    inner = cover(d_shape)
    return a, inner


def save(name, width, height, pixels, channels=4):
    path = os.path.join(TEX_DIR, name)
    write_png(path, width, height, pixels, channels)
    return f"textures/{name}"


def gen_paper():
    def shade(u, v, x, y):
        d = sd_circle(x, y, 0.8)
        a, inner = sticker_shape(d)
        ds = sd_polygon(x, y, star(5, 0.62, 0.26))
        bg = lerp((0.95, 0.91, 0.78), (0.86, 0.76, 0.58), smooth(0.0, 0.8, math.hypot(x, y)))
        c = lerp(bg, (0.93, 0.36, 0.12), cover(ds))
        c = lerp(c, (0.12, 0.1, 0.1), cover(abs(ds) - 0.018))
        c = lerp((1, 1, 1), c, inner)
        return (*c, a)
    return {"base": save("demo_paper_star_color.png", SIZE, SIZE, render(SIZE, SIZE, shade))}


def gen_glitter():
    pts = heart()

    def shade(u, v, x, y):
        d = sd_polygon(x, y, pts)
        a, inner = sticker_shape(d)
        c = lerp((0.98, 0.35, 0.62), (0.7, 0.1, 0.4), smooth(-0.6, 0.6, y))
        c = lerp((1, 1, 1), c, inner)
        return (*c, a)

    def mask(u, v, x, y):
        d = sd_polygon(x, y, pts)
        return (cover(d + 0.05),)  # glitter inside the heart, not on the border
    return {
        "base": save("demo_glitter_heart_color.png", SIZE, SIZE, render(SIZE, SIZE, shade)),
        "glitter": save("demo_glitter_heart_glitter.png", SIZE, SIZE, render(SIZE, SIZE, mask), 1),
    }


def gen_holo():
    def rings(x, y):
        r = math.hypot(x, y)
        return cover(abs(math.sin(r * 18.0)) - 0.55, 0.12) * cover(r - 0.72)

    def shade(u, v, x, y):
        d = sd_circle(x, y, 0.8)
        a, inner = sticker_shape(d)
        c = lerp((0.1, 0.16, 0.35), (0.78, 0.82, 0.9), rings(x, y))
        c = lerp((1, 1, 1), c, inner)
        return (*c, a)

    def mask(u, v, x, y):
        # R strength, G/B spectrum offset (radial + angular), A multiplier.
        inner = cover(sd_circle(x, y, 0.8))
        strength = max(rings(x, y), 0.25) * inner
        ang = (math.atan2(y, x) / (2 * math.pi)) % 1.0
        return (strength, math.hypot(x, y) * 0.8, ang, 1.0)

    def spectrum(u, v, x, y):
        h = u * 6.0
        k = lambda n: max(0.0, min(1.0, abs((h + n) % 6 - 3) - 1))  # noqa: E731
        return (k(0), k(4), k(2), 1.0)
    return {
        "base": save("demo_holo_rings_color.png", SIZE, SIZE, render(SIZE, SIZE, shade)),
        "holomask": save("demo_holo_rings_holomask.png", SIZE, SIZE, render(SIZE, SIZE, mask)),
        "holospectrum": save("demo_holo_rings_holospectrum.png", SIZE, 16, render(SIZE, 16, spectrum)),
    }


def _embossed(name, pts, color_a, color_b, detail):
    hmap = []

    def shade(u, v, x, y):
        d = sd_polygon(x, y, pts)
        a, inner = sticker_shape(d)
        e = detail(x, y)
        c = lerp(color_a, color_b, 0.5 + 0.5 * y)
        c = lerp(c, tuple(min(1, ch * 1.25) for ch in c), e)
        c = lerp((0.9, 0.9, 0.9), c, inner)
        # Height: raised rim + raised detail.
        hmap.append(smooth(0.0, -0.08, d) * 0.6 + e * 0.4 * inner)
        return (*c, a)
    base = save(f"{name}_color.png", SIZE, SIZE, render(SIZE, SIZE, shade))
    normal = save(f"{name}_normal.png", SIZE, SIZE, normal_from_height(SIZE, SIZE, hmap, 6.0), 3)
    return {"base": base, "normal": normal}


def gen_foil():
    def chevron(x, y):
        d = sd_polygon(x, y, [(-0.45, 0.35), (0.0, -0.05), (0.45, 0.35), (0.45, 0.1),
                              (0.0, -0.3), (-0.45, 0.1)])
        return cover(d, 0.03)
    return _embossed("demo_foil_shield", SHIELD, (0.62, 0.66, 0.72), (0.9, 0.92, 0.95), chevron)


def gen_gold():
    def jewels(x, y):
        return max(cover(sd_circle(x - px, y + 0.25, 0.09), 0.03) for px in (-0.45, 0.0, 0.45))
    return _embossed("demo_gold_crown", CROWN, (0.75, 0.62, 0.35), (0.95, 0.88, 0.6), jewels)


def gen_lenticular():
    frames = 2
    width = SIZE * frames
    eye = ellipse(0.75, 0.42)

    def shade(u, v, x, y):
        frame = min(int(u * frames), frames - 1)
        fx = x - frame * 2  # x per frame in -1..1
        d = sd_circle(fx, y, 0.85)
        a, inner = sticker_shape(d)
        c = (0.12, 0.6, 0.55)
        if frame == 0:  # open eye
            c = lerp(c, (0.97, 0.97, 0.95), cover(sd_polygon(fx, y, eye)))
            c = lerp(c, (0.15, 0.25, 0.7), cover(sd_circle(fx, y, 0.3)))
            c = lerp(c, (0.02, 0.02, 0.03), cover(sd_circle(fx, y, 0.13)))
        else:  # closed eye: lid line
            lid = abs(math.hypot(fx, y + 0.9) - 0.95) - 0.035
            c = lerp(c, (0.02, 0.05, 0.05), cover(max(lid, abs(fx) - 0.7)))
        c = lerp((1, 1, 1), c, inner)
        return (*c, a)
    return {"base": save("demo_lenticular_eye_color.png", width, SIZE, render(width, SIZE, shade))}, \
        {"frames": frames}


def gen_embroidered():
    hexagon = regular(6, 0.85, math.pi / 6)
    hmap = []

    def shade(u, v, x, y):
        d = sd_polygon(x, y, hexagon)
        a = cover(d)
        rim = cover(d + 0.12) < 0.5  # stitched border band (outer 0.12)
        ds = sd_polygon(x, y, star(4, 0.5, 0.18, math.pi / 4))
        if rim:
            c = (0.85, 0.7, 0.2)
        elif cover(ds) > 0.5:
            c = (0.9, 0.9, 0.88)
        else:
            c = (0.12, 0.2, 0.42)
        hmap.append((0.9 if rim else 0.5 + 0.3 * cover(ds)) * a)
        return (*c, a)
    base = save("demo_embroidered_patch_color.png", SIZE, SIZE, render(SIZE, SIZE, shade))
    normal = save("demo_embroidered_patch_normal.png", SIZE, SIZE, normal_from_height(SIZE, SIZE, hmap, 3.0), 3)
    return {"base": base, "normal": normal}


def main():
    os.makedirs(TEX_DIR, exist_ok=True)
    lent_tex, lent_params = gen_lenticular()
    entries = [
        ("demo_paper_star", "Demo Star", "PAPER", gen_paper(), {}, ["demo", "star"]),
        ("demo_glitter_heart", "Demo Heart", "GLITTER", gen_glitter(), {}, ["demo", "heart"]),
        ("demo_holo_rings", "Demo Rings", "HOLO", gen_holo(), {}, ["demo", "rings"]),
        ("demo_foil_shield", "Demo Shield", "FOIL", gen_foil(), {}, ["demo", "shield"]),
        ("demo_gold_crown", "Demo Crown", "GOLD", gen_gold(), {}, ["demo", "crown"]),
        ("demo_lenticular_eye", "Demo Eye", "LENTICULAR", lent_tex, lent_params, ["demo", "eye"]),
        ("demo_embroidered_patch", "Demo Patch", "EMBROIDERED", gen_embroidered(), {}, ["demo", "patch"]),
    ]
    catalog = {
        "version": 1,
        "collection": COLLECTION,
        "stickers": [
            {"id": sid, "name": name, "collection": COLLECTION, "finish": finish,
             "textures": tex, "params": params, "tags": tags}
            for sid, name, finish, tex, params, tags in entries
        ],
    }
    with open(os.path.join(OUT_DIR, "catalog.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(catalog, fh, indent=2)
        fh.write("\n")
    print(f"wrote {len(entries)} demo stickers to {OUT_DIR}")


if __name__ == "__main__":
    main()
