#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate deterministic synthetic RGB fixtures for pixel / tile / archive benches.

Design (why not solid colours)
------------------------------
Solid or single-ramp images compress to a few KB and under-stress Huffman/IDCT,
tile encode, and shrink-on-load. Real library traffic is photos, scans, comics,
UI screenshots, and mixed pages. This generator builds **named content classes**
so each bench row answers a specific question.

Classes
-------
photo     Multi-octave value noise + low-frequency colour washes + fine grain.
          Moderate entropy — stand-in for camera JPEGs.
text      Black bitmap text on white with margins and a rule line.
          Hard edges, large flat runs — JPEG's awkward case; still non-trivial decode.
geometry  Circles, rectangles, diagonals, checker patch on a light field.
          Mix of flats and hard edges; good tile-boundary stress.
fractal   Mandelbrot escape-time colouring.
          Detail at every scale — exercises shrink vs full decode quality/cost.
noise     High-frequency deterministic hash noise.
          Upper bound on encode size and decode work.
mixed     One "page": gradient header, text block, geometry, photo-noise panel.
          Single-image proxy for document / gallery mixed content.

Sizes (default)
---------------
800×600   smoke / CI
1920×1080 primary matrix
3840×2160 large (omit with --no-large)

Outputs JPEG q90 + PNG under synthetic/{jpeg,png}/; manifest.json lists class,
size, and intent. All RNGs are seeded by (class, width, height) so bytes are
stable for a given generator version.

Requires: numpy, Pillow (encode); optional ``vips`` not required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Default matrix: smoke + primary + one large. 8K is opt-in (slow + big).
DEFAULT_SIZES = [
    (800, 600),
    (1920, 1080),
    (3840, 2160),
]

JPEG_Q = 90

# 5×7 style glyphs for "text" class (A-Z, 0-9, space, limited punct).
# Rows are top→bottom; bits are left→right MSB.
_GLYPHS: dict[str, list[str]] = {
    " ": ["00000"] * 7,
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10001", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10001", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    ",": ["00000", "00000", "00000", "00000", "01100", "00100", "01000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "/": ["00001", "00010", "00100", "01000", "10000", "10000", "10000"],
}


def _seed_u32(*parts: object) -> int:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\0")
    return int.from_bytes(h.digest()[:4], "little")


def _rng(*parts: object) -> np.random.Generator:
    return np.random.default_rng(_seed_u32(*parts))


def _value_noise(h: int, w: int, rng: np.random.Generator, cell: int) -> np.ndarray:
    """Smooth value noise in [0, 1], shape (h, w)."""
    gh = max(2, h // cell + 2)
    gw = max(2, w // cell + 2)
    grid = rng.random((gh, gw), dtype=np.float64)
    ys = np.linspace(0, gh - 2, h)
    xs = np.linspace(0, gw - 2, w)
    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    fy = ys - y0
    fx = xs - x0
    # Hermite smoothstep
    sy = fy * fy * (3.0 - 2.0 * fy)
    sx = fx * fx * (3.0 - 2.0 * fx)
    y0 = y0.reshape(-1, 1)
    sy = sy.reshape(-1, 1)
    # bilinear on grid
    g00 = grid[y0, x0]
    g10 = grid[y0, x0 + 1]
    g01 = grid[y0 + 1, x0]
    g11 = grid[y0 + 1, x0 + 1]
    top = g00 * (1 - sx) + g10 * sx
    bot = g01 * (1 - sx) + g11 * sx
    return top * (1 - sy) + bot * sy


def _to_u8(img: np.ndarray) -> np.ndarray:
    return np.clip(img, 0, 255).astype(np.uint8)


def render_photo(w: int, h: int) -> np.ndarray:
    """Camera-like: coloured low-freq washes + multi-octave luminance noise + grain."""
    rng = _rng("photo", w, h)
    # Low-frequency colour field (3 octaves of coarse noise per channel)
    base = np.zeros((h, w, 3), dtype=np.float64)
    for c, cell, amp, bias in (
        (0, max(w // 6, 8), 70.0, 90.0),
        (1, max(w // 5, 8), 55.0, 100.0),
        (2, max(w // 7, 8), 65.0, 110.0),
    ):
        base[:, :, c] = bias + amp * _value_noise(h, w, rng, cell)
    # Luminance detail octaves
    lum = np.zeros((h, w), dtype=np.float64)
    for cell, amp in (
        (max(w // 16, 4), 40.0),
        (max(w // 40, 3), 22.0),
        (max(w // 90, 2), 12.0),
    ):
        lum += amp * (_value_noise(h, w, rng, cell) - 0.5)
    for c in range(3):
        base[:, :, c] += lum
    # Fine grain
    grain = rng.normal(0.0, 4.0, size=(h, w, 3))
    base += grain
    return _to_u8(base)


def render_text(w: int, h: int) -> np.ndarray:
    """Black bitmap text on white — hard edges, large flats (JPEG stress case)."""
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    margin = max(16, min(w, h) // 20)
    # Title + body lines (deterministic copy)
    lines = [
        "PIXEL BENCH CORPUS — TEXT CLASS",
        "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG 0123456789",
        "HARD EDGES AND FLAT RUNS STRESS JPEG RINGING AND HUFFMAN",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "SIZE {}X{} DETERMINISTIC BITMAP FONT".format(w, h),
        "REPEATED LINE FOR VERTICAL COVERAGE " * 2,
        "PACKED ROWS: IIIILLLLOOOOMMMMNNNN / 1234567890",
        "END OF SAMPLE PAGE",
    ]
    # Scale glyph so ~40–60 chars fit on a line when possible
    scale = max(1, min(4, (w - 2 * margin) // (5 * 48)))
    glyph_w = 5 * scale
    glyph_h = 7 * scale
    gap_x = max(1, scale)
    gap_y = max(2, scale * 2)
    y = margin
    for line in lines:
        if y + glyph_h >= h - margin:
            break
        x = margin
        for ch in line.upper():
            if x + glyph_w >= w - margin:
                break
            pattern = _GLYPHS.get(ch, _GLYPHS[" "])
            for gy, row in enumerate(pattern):
                for gx, bit in enumerate(row):
                    if bit != "1":
                        continue
                    y0 = y + gy * scale
                    x0 = x + gx * scale
                    img[y0 : y0 + scale, x0 : x0 + scale, :] = 0
            x += glyph_w + gap_x
        y += glyph_h + gap_y
    # Horizontal rule under title area
    ry = margin + glyph_h + gap_y // 2
    if 0 <= ry < h:
        img[ry : ry + max(1, scale // 2), margin : w - margin, :] = 40
    return img


def render_geometry(w: int, h: int) -> np.ndarray:
    """Shapes on a light field: flats + hard edges + checker patch."""
    rng = _rng("geometry", w, h)
    # Light grey background with slight vignette-ish vertical gradient
    yy = np.linspace(0, 1, h).reshape(-1, 1)
    bg = 230 - 25 * yy
    img = np.stack([bg, bg, bg + 5], axis=2)
    img = np.broadcast_to(img, (h, w, 3)).copy()

    yy_i, xx_i = np.mgrid[0:h, 0:w]

    def disk(cx, cy, r, color, fill=True, width=2):
        d2 = (xx_i - cx) ** 2 + (yy_i - cy) ** 2
        if fill:
            m = d2 <= r * r
        else:
            m = (d2 <= r * r) & (d2 >= (r - width) ** 2)
        img[m] = color

    def rect(x0, y0, x1, y1, color, fill=True, width=2):
        if fill:
            img[y0:y1, x0:x1] = color
        else:
            img[y0 : y0 + width, x0:x1] = color
            img[y1 - width : y1, x0:x1] = color
            img[y0:y1, x0 : x0 + width] = color
            img[y0:y1, x1 - width : x1] = color

    # Checker patch (top-left)
    cs = max(8, min(w, h) // 24)
    for iy in range(0, h // 3, cs):
        for ix in range(0, w // 3, cs):
            if ((ix // cs) + (iy // cs)) % 2 == 0:
                img[iy : iy + cs, ix : ix + cs] = (20, 20, 20)

    # Filled / outline circles
    disk(int(w * 0.7), int(h * 0.35), min(w, h) // 6, (200, 40, 40), True)
    disk(int(w * 0.55), int(h * 0.55), min(w, h) // 8, (40, 40, 200), False, width=max(2, min(w, h) // 120))
    disk(int(w * 0.3), int(h * 0.65), min(w, h) // 10, (40, 160, 60), True)

    # Rectangles
    rect(int(w * 0.1), int(h * 0.4), int(w * 0.35), int(h * 0.55), (180, 120, 20), True)
    rect(int(w * 0.65), int(h * 0.7), int(w * 0.9), int(h * 0.9), (30, 30, 30), False, width=max(2, min(w, h) // 100))

    # Diagonals
    for t in range(0, max(w, h), max(2, min(w, h) // 200)):
        x = t
        y = t * h // max(w, 1)
        if 0 <= y < h and 0 <= x < w:
            img[y, max(0, x - 1) : min(w, x + 2)] = (0, 0, 0)
        x2 = w - 1 - t
        y2 = t * h // max(w, 1)
        if 0 <= y2 < h and 0 <= x2 < w:
            img[y2, max(0, x2 - 1) : min(w, x2 + 2)] = (80, 0, 80)

    # A few random small filled boxes (seeded)
    for _ in range(12):
        bw = int(rng.integers(w // 40, max(w // 40 + 1, w // 15)))
        bh = int(rng.integers(h // 40, max(h // 40 + 1, h // 15)))
        x0 = int(rng.integers(0, max(1, w - bw)))
        y0 = int(rng.integers(0, max(1, h - bh)))
        color = tuple(int(c) for c in rng.integers(0, 255, size=3))
        img[y0 : y0 + bh, x0 : x0 + bw] = color

    return _to_u8(img)


def render_fractal(w: int, h: int) -> np.ndarray:
    """Mandelbrot — detail at all scales (shrink vs full decode)."""
    # Viewpoint chosen for interesting structure (classic seahorse-ish crop)
    x0, x1 = -2.0, 1.0
    y0, y1 = -1.2, 1.2
    max_iter = 80 if max(w, h) <= 2000 else 64
    xs = np.linspace(x0, x1, w, dtype=np.float64)
    ys = np.linspace(y0, y1, h, dtype=np.float64)
    c = xs[np.newaxis, :] + 1j * ys[:, np.newaxis]
    z = np.zeros_like(c)
    esc = np.full((h, w), max_iter, dtype=np.int32)
    active = np.ones((h, w), dtype=bool)
    for i in range(max_iter):
        z[active] = z[active] * z[active] + c[active]
        escaped = active & (np.abs(z) > 2.0)
        esc[escaped] = i
        active &= ~escaped
        if not np.any(active):
            break
    t = esc.astype(np.float64) / max_iter
    # Smooth-ish palette
    r = _to_u8(9 * (1 - t) * t * t * t * 255)
    g = _to_u8(15 * (1 - t) * (1 - t) * t * t * 255)
    b = _to_u8(8.5 * (1 - t) * (1 - t) * (1 - t) * t * 255)
    # Interior black
    interior = esc == max_iter
    r[interior] = 0
    g[interior] = 0
    b[interior] = 0
    return np.stack([r, g, b], axis=2)


def render_noise(w: int, h: int) -> np.ndarray:
    """High-frequency deterministic noise — encode-size / decode upper bound."""
    rng = _rng("noise", w, h)
    return rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)


def render_mixed(w: int, h: int) -> np.ndarray:
    """Page-like composite: header gradient, text, geometry inset, photo panel."""
    img = np.full((h, w, 3), 245, dtype=np.uint8)
    # Header gradient band
    hh = max(h // 8, 24)
    for y in range(hh):
        t = y / max(hh - 1, 1)
        img[y, :] = (
            int(30 + 40 * t),
            int(60 + 80 * t),
            int(120 + 100 * t),
        )
    # Photo-noise panel on the right half below header
    panel = render_photo(w // 2, h - hh)
    img[hh:h, w // 2 : w // 2 + panel.shape[1]] = panel[:, : w - w // 2]
    # Geometry strip left-bottom
    geo_h = (h - hh) // 2
    geo = render_geometry(w // 2, geo_h)
    img[hh + (h - hh) // 2 : hh + (h - hh) // 2 + geo_h, 0 : w // 2] = geo[:, : w // 2]
    # Text on upper-left content area (draw onto white then blit)
    text_h = (h - hh) // 2
    text = render_text(w // 2, text_h)
    img[hh : hh + text_h, 0 : w // 2] = text[:, : w // 2]
    # Thin divider lines
    img[hh : hh + 2, :] = 20
    img[hh:, w // 2 : w // 2 + 2] = 20
    return img


CLASSES = {
    "photo": {
        "fn": render_photo,
        "intent": "camera-like multi-octave noise; typical JPEG path",
    },
    "text": {
        "fn": render_text,
        "intent": "black bitmap text on white; hard edges + flat runs",
    },
    "geometry": {
        "fn": render_geometry,
        "intent": "circles/rects/checker; flats + hard edges",
    },
    "fractal": {
        "fn": render_fractal,
        "intent": "Mandelbrot; detail at all scales for shrink vs full",
    },
    "noise": {
        "fn": render_noise,
        "intent": "high-frequency noise; encode/decode upper bound",
    },
    "mixed": {
        "fn": render_mixed,
        "intent": "page composite: gradient + text + geometry + photo panel",
    },
}


def save_png(rgb: np.ndarray, path: Path) -> None:
    Image.fromarray(np.ascontiguousarray(rgb), mode="RGB").save(
        path, format="PNG", optimize=False
    )


def save_jpeg(rgb: np.ndarray, path: Path, quality: int) -> None:
    # optimize=True can fail on full-entropy noise with some libjpeg builds
    # ("broken data stream"); disable for reliability and stable timings.
    Image.fromarray(np.ascontiguousarray(rgb), mode="RGB").save(
        path, format="JPEG", quality=quality, optimize=False, subsampling=0
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, required=True, help="output root directory")
    ap.add_argument(
        "--classes",
        type=str,
        default=",".join(CLASSES.keys()),
        help="comma-separated class names (default: all)",
    )
    ap.add_argument(
        "--no-large",
        action="store_true",
        help="omit 3840×2160 (faster smoke builds)",
    )
    ap.add_argument(
        "--with-8k",
        action="store_true",
        help="also generate 7680×4320 (slow, large)",
    )
    args = ap.parse_args()

    sizes = list(DEFAULT_SIZES)
    if args.no_large:
        sizes = [(w, h) for w, h in sizes if w * h < 4_000_000]
    if args.with_8k:
        sizes.append((7680, 4320))

    class_names = [c.strip() for c in args.classes.split(",") if c.strip()]
    for c in class_names:
        if c not in CLASSES:
            print(f"unknown class: {c} (want {list(CLASSES)})", file=sys.stderr)
            return 2

    root: Path = args.out
    jpeg_dir = root / "synthetic" / "jpeg"
    png_dir = root / "synthetic" / "png"
    jpeg_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    for cls in class_names:
        meta = CLASSES[cls]
        for w, h in sizes:
            rgb = meta["fn"](w, h)
            if rgb.shape != (h, w, 3):
                raise RuntimeError(f"{cls} produced {rgb.shape}, expected {(h, w, 3)}")
            stem = f"{cls}_{w}x{h}"
            png_path = png_dir / f"{stem}.png"
            jpg_path = jpeg_dir / f"{stem}_q{JPEG_Q}.jpg"
            save_png(rgb, png_path)
            save_jpeg(rgb, jpg_path, JPEG_Q)
            mpix = (w * h) / 1e6
            jpg_bytes = jpg_path.stat().st_size
            for path, codec in ((png_path, "png"), (jpg_path, "jpeg")):
                entries.append(
                    {
                        "id": f"{stem}_{codec}",
                        "path": str(path.relative_to(root)),
                        "class": cls,
                        "codec": codec,
                        "width": w,
                        "height": h,
                        "mpix": round(mpix, 3),
                        "bands": 3,
                        "jpeg_bytes": jpg_bytes if codec == "jpeg" else None,
                        "license": "GPL-3.0-or-later",
                        "intent": meta["intent"],
                    }
                )
            print(
                f"wrote {jpg_path.name} ({mpix:.2f} MP, jpeg={jpg_bytes} B) — {meta['intent']}",
                file=sys.stderr,
            )

    manifest = {
        "schema": 2,
        "generator": "gen_synthetic.py",
        "generator_note": "content-class matrix (photo/text/geometry/fractal/noise/mixed)",
        "entries": entries,
    }
    man_path = root / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest entries={len(entries)} -> {man_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
