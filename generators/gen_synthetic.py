#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate deterministic synthetic RGB fixtures for pixel / tile / archive benches.

Design
------
Solid fills and single ramps under-stress Huffman/IDCT and tile encode. Biltoo
is largely an **ebook / comic / image-album** viewer, so the matrix includes
portrait book pages, landscape photos, comic panels, and two-page spreads as
well as generic photo/text/geometry stress cases.

Content classes
---------------
photo       Landscape-leaning multi-octave noise + colour washes + grain.
landscape   Explicit wide scene: sky gradient, horizon, terrain noise, sun disk.
bookpage    Portrait page: cream paper, dense body text, header, page number.
spread      Landscape open-book: two pages, centre gutter, dual text columns.
comic       Portrait panel grid, gutters, caption/speech blocks, ink flats.
scan        Bookpage + paper grain + soft vignette (scanned-page proxy).
text        High-contrast black-on-white UI/screenshot text (JPEG ringing).
geometry    Shapes + checker (flats and hard edges).
fractal     Mandelbrot (detail at every scale).
noise       Full-entropy upper bound.
mixed       Composite “gallery tile”: header + text + geometry + photo panel.

Aspect sets
-----------
landscape  16:9 — 800×450, 1920×1080, 3840×2160
portrait   ~2:3 — 600×900, 1200×1800, 1600×2400
Each class picks the set that matches real files of that kind. ``--no-large``
drops the largest size in each set; ``--with-8k`` adds 7680×4320 landscape only.

Every image gets a bottom banner with class, resolution, and purpose so fixtures
are self-explanatory in a viewer. Seeds are ``(class, width, height)`` so output
is stable for a generator version.

Requires: numpy, Pillow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# --- size sets ----------------------------------------------------------------

SIZES_LANDSCAPE = [
    (800, 450),
    (1920, 1080),
    (3840, 2160),
]

SIZES_PORTRAIT = [
    (600, 900),
    (1200, 1800),
    (1600, 2400),
]

JPEG_Q = 90

# 5×7 bitmap glyphs (A-Z, 0-9, space, limited punct).
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
    "'": ["01100", "01100", "00100", "00000", "00000", "00000", "00000"],
    '"': ["01010", "01010", "00000", "00000", "00000", "00000", "00000"],
    "(": ["00100", "01000", "10000", "10000", "10000", "01000", "00100"],
    ")": ["00100", "00010", "00001", "00001", "00001", "00010", "00100"],
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
    sy = fy * fy * (3.0 - 2.0 * fy)
    sx = fx * fx * (3.0 - 2.0 * fx)
    y0 = y0.reshape(-1, 1)
    sy = sy.reshape(-1, 1)
    g00 = grid[y0, x0]
    g10 = grid[y0, x0 + 1]
    g01 = grid[y0 + 1, x0]
    g11 = grid[y0 + 1, x0 + 1]
    top = g00 * (1 - sx) + g10 * sx
    bot = g01 * (1 - sx) + g11 * sx
    return top * (1 - sy) + bot * sy


def _to_u8(img: np.ndarray) -> np.ndarray:
    return np.clip(img, 0, 255).astype(np.uint8)


def _blit_text(
    img: np.ndarray,
    lines: list[str],
    *,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int] = (20, 20, 20),
    scale: int | None = None,
    line_gap: int | None = None,
) -> None:
    """Draw bitmap text into img[y0:y1, x0:x1] clipping to the box."""
    box_w = max(1, x1 - x0)
    box_h = max(1, y1 - y0)
    if scale is None:
        # Fit ~55 glyphs per line when possible
        scale = max(1, min(5, box_w // (5 * 55)))
    glyph_w = 5 * scale
    glyph_h = 7 * scale
    gap_x = max(1, scale)
    gap_y = line_gap if line_gap is not None else max(2, scale * 2 + 1)
    y = y0
    for line in lines:
        if y + glyph_h > y1:
            break
        x = x0
        for ch in line.upper():
            if x + glyph_w > x1:
                break
            pattern = _GLYPHS.get(ch, _GLYPHS[" "])
            for gy, row in enumerate(pattern):
                for gx, bit in enumerate(row):
                    if bit != "1":
                        continue
                    py = y + gy * scale
                    px = x + gx * scale
                    if py + scale > y1 or px + scale > x1:
                        continue
                    img[py : py + scale, px : px + scale, :] = color
            x += glyph_w + gap_x
        y += glyph_h + gap_y


def _paragraph_lines(seed_key: str, n_lines: int, width_chars: int) -> list[str]:
    """Deterministic pseudo-prose lines for book-like density."""
    words = (
        "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG WHILE THE "
        "SHIP OF THE DESERT CROSSES ANOTHER DUNE UNDER A PALE SKY "
        "CHAPTER NOTES RECALL THAT READERS OF EBOOKS AND COMICS "
        "STRESS TILE PIPELINES DIFFERENTLY THAN CAMERA PHOTOS "
        "MARGINS COLUMNS AND GUTTERS MATTER FOR PAGE LAYOUT "
        "BILTOO OPENS ARCHIVES OF PAGES SCANS AND SPREADS "
    ).split()
    rng = _rng("prose", seed_key)
    lines: list[str] = []
    i = int(rng.integers(0, len(words)))
    for _ in range(n_lines):
        buf: list[str] = []
        length = 0
        while length < width_chars:
            w = words[i % len(words)]
            i += 1
            if length + len(w) + (1 if buf else 0) > width_chars:
                break
            buf.append(w)
            length += len(w) + (1 if len(buf) > 1 else 0)
        if not buf:
            buf = [words[i % len(words)]]
            i += 1
        lines.append(" ".join(buf))
    return lines


# --- renderers ----------------------------------------------------------------


def render_photo(w: int, h: int) -> np.ndarray:
    """Camera-like colour field; works at any aspect (usually landscape sizes)."""
    rng = _rng("photo", w, h)
    base = np.zeros((h, w, 3), dtype=np.float64)
    for c, cell, amp, bias in (
        (0, max(w // 6, 8), 70.0, 90.0),
        (1, max(w // 5, 8), 55.0, 100.0),
        (2, max(w // 7, 8), 65.0, 110.0),
    ):
        base[:, :, c] = bias + amp * _value_noise(h, w, rng, cell)
    lum = np.zeros((h, w), dtype=np.float64)
    for cell, amp in (
        (max(w // 16, 4), 40.0),
        (max(w // 40, 3), 22.0),
        (max(w // 90, 2), 12.0),
    ):
        lum += amp * (_value_noise(h, w, rng, cell) - 0.5)
    for c in range(3):
        base[:, :, c] += lum
    base += rng.normal(0.0, 4.0, size=(h, w, 3))
    return _to_u8(base)


def render_landscape(w: int, h: int) -> np.ndarray:
    """Wide scenic proxy: sky gradient, sun, horizon, terrain noise."""
    rng = _rng("landscape", w, h)
    yy = np.linspace(0, 1, h).reshape(-1, 1)
    # Sky (upper ~55%)
    sky_r = 40 + 120 * (1 - yy)
    sky_g = 80 + 100 * (1 - yy)
    sky_b = 140 + 90 * (1 - yy)
    img = np.stack(
        [
            np.broadcast_to(sky_r, (h, w)),
            np.broadcast_to(sky_g, (h, w)),
            np.broadcast_to(sky_b, (h, w)),
        ],
        axis=2,
    ).astype(np.float64)
    # Sun disk
    cy, cx = int(h * 0.22), int(w * 0.72)
    radius = max(h // 12, 8)
    yy_i, xx_i = np.mgrid[0:h, 0:w]
    d2 = (xx_i - cx) ** 2 + (yy_i - cy) ** 2
    sun = d2 <= radius * radius
    img[sun] = (250, 230, 120)
    glow = (d2 <= (radius * 2.2) ** 2) & ~sun
    img[glow] = img[glow] * 0.7 + np.array([250, 220, 100]) * 0.3
    # Terrain below horizon
    horizon = int(h * 0.55)
    terrain = _value_noise(h - horizon, w, rng, max(w // 20, 4))
    terrain2 = _value_noise(h - horizon, w, rng, max(w // 50, 3))
    ground = np.zeros((h - horizon, w, 3), dtype=np.float64)
    ground[:, :, 0] = 50 + 80 * terrain + 30 * terrain2
    ground[:, :, 1] = 70 + 90 * terrain + 20 * terrain2
    ground[:, :, 2] = 40 + 40 * terrain
    img[horizon:h, :, :] = ground
    # Soft horizon line
    img[horizon : horizon + 2, :, :] *= 0.85
    img += rng.normal(0.0, 2.5, size=img.shape)
    return _to_u8(img)


def render_bookpage(w: int, h: int) -> np.ndarray:
    """Portrait book page: cream paper, title, dense body, page number."""
    # Cream paper
    img = np.empty((h, w, 3), dtype=np.float64)
    img[:, :, 0] = 248
    img[:, :, 1] = 244
    img[:, :, 2] = 232
    # Slight vertical paper tone
    yy = np.linspace(0, 1, h).reshape(-1, 1, 1)
    img = img + (yy - 0.5) * 4.0
    img = _to_u8(img)

    margin_x = max(w // 10, 24)
    margin_top = max(h // 12, 28)
    margin_bot = max(h // 14, 32)
    # Header
    _blit_text(
        img,
        ["CHAPTER 12 — THE ARCHIVE"],
        x0=margin_x,
        y0=margin_top // 2,
        x1=w - margin_x,
        y1=margin_top,
        color=(40, 30, 20),
    )
    # Rule under header
    ry = margin_top - 4
    if 0 <= ry < h:
        img[ry : ry + max(1, h // 400), margin_x : w - margin_x, :] = (120, 100, 80)

    # Body: estimate scale and fill lines
    scale = max(1, min(4, (w - 2 * margin_x) // (5 * 52)))
    glyph_h = 7 * scale
    gap_y = max(2, scale * 2)
    line_pitch = glyph_h + gap_y
    usable = h - margin_top - margin_bot
    n_lines = max(4, usable // line_pitch)
    width_chars = max(20, (w - 2 * margin_x) // (5 * scale + max(1, scale)))
    lines = _paragraph_lines(f"bookpage-{w}x{h}", n_lines, width_chars)
    _blit_text(
        img,
        lines,
        x0=margin_x,
        y0=margin_top,
        x1=w - margin_x,
        y1=h - margin_bot,
        color=(25, 22, 18),
        scale=scale,
        line_gap=gap_y,
    )
    # Page number centred at bottom
    pn = f"- {((w * h) // 1000) % 900 + 100} -"
    _blit_text(
        img,
        [pn],
        x0=w // 2 - 40 * scale,
        y0=h - margin_bot + 4,
        x1=w // 2 + 40 * scale,
        y1=h - 4,
        color=(80, 70, 60),
        scale=max(1, scale),
    )
    return img


def render_spread(w: int, h: int) -> np.ndarray:
    """Landscape two-page spread with centre gutter."""
    img = np.empty((h, w, 3), dtype=np.float64)
    img[:, :, 0] = 246
    img[:, :, 1] = 242
    img[:, :, 2] = 230
    img = _to_u8(img)

    gutter = max(w // 40, 6)
    mid = w // 2
    # Gutter shadow
    img[:, mid - gutter // 2 : mid + gutter // 2, :] = (200, 195, 180)
    img[:, mid - 1 : mid + 1, :] = (160, 150, 130)

    margin = max(min(w, h) // 16, 16)
    scale = max(1, min(3, (mid - 2 * margin) // (5 * 40)))
    gap_y = max(2, scale * 2)
    glyph_h = 7 * scale
    n_lines = max(3, (h - 2 * margin) // (glyph_h + gap_y))
    width_chars = max(16, (mid - 2 * margin) // (5 * scale + max(1, scale)))

    for side, x0, x1, key in (
        ("L", margin, mid - gutter, "spread-L"),
        ("R", mid + gutter, w - margin, "spread-R"),
    ):
        header = [f"{'VERSO' if side == 'L' else 'RECTO'} — SAMPLE SPREAD"]
        _blit_text(
            img,
            header,
            x0=x0,
            y0=margin // 2,
            x1=x1,
            y1=margin,
            color=(50, 40, 30),
            scale=scale,
        )
        body = _paragraph_lines(f"{key}-{w}x{h}", n_lines, width_chars)
        _blit_text(
            img,
            body,
            x0=x0,
            y0=margin,
            x1=x1,
            y1=h - margin,
            color=(30, 25, 20),
            scale=scale,
            line_gap=gap_y,
        )
    return img


def render_comic(w: int, h: int) -> np.ndarray:
    """Portrait comic/manga-style panel page."""
    # Off-white page
    img = np.full((h, w, 3), 250, dtype=np.uint8)
    margin = max(min(w, h) // 30, 8)
    gutter = max(min(w, h) // 50, 4)
    # 2×3 panel grid (common portrait comic layout)
    cols, rows = 2, 3
    inner_w = w - 2 * margin - (cols - 1) * gutter
    inner_h = h - 2 * margin - (rows - 1) * gutter
    pw, ph = inner_w // cols, inner_h // rows
    rng = _rng("comic", w, h)

    for r in range(rows):
        for c in range(cols):
            x0 = margin + c * (pw + gutter)
            y0 = margin + r * (ph + gutter)
            x1, y1 = x0 + pw, y0 + ph
            # Panel border
            img[y0:y1, x0 : x0 + 2, :] = 0
            img[y0:y1, x1 - 2 : x1, :] = 0
            img[y0 : y0 + 2, x0:x1, :] = 0
            img[y1 - 2 : y1, x0:x1, :] = 0
            # Panel fill: alternate ink wash / photo-ish / flat
            kind = (r * cols + c) % 3
            inset = 3
            if kind == 0:
                # Flat screen tone + circle “character”
                img[y0 + inset : y1 - inset, x0 + inset : x1 - inset] = (
                    230,
                    230,
                    235,
                )
                cy = (y0 + y1) // 2
                cx = (x0 + x1) // 2
                rad = min(pw, ph) // 5
                yy, xx = np.ogrid[y0:y1, x0:x1]
                disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= rad * rad
                panel = img[y0:y1, x0:x1]
                panel[disk] = (30, 30, 40)
            elif kind == 1:
                # Speed-line-ish diagonals
                panel = np.full((y1 - y0, x1 - x0, 3), 245, dtype=np.uint8)
                for t in range(0, max(pw, ph), max(3, min(pw, ph) // 30)):
                    for thickness in range(max(1, min(pw, ph) // 80)):
                        y = t + thickness
                        if 0 <= y < panel.shape[0]:
                            panel[y, :] = (20, 20, 20)
                img[y0:y1, x0:x1] = panel
            else:
                # Mini photo noise
                sub = render_photo(x1 - x0 - 2 * inset, y1 - y0 - 2 * inset)
                img[y0 + inset : y1 - inset, x0 + inset : x1 - inset] = sub
            # Speech / caption box in lower third of some panels
            if (r + c) % 2 == 0:
                bx0 = x0 + pw // 8
                by0 = y1 - ph // 3
                bx1 = x1 - pw // 8
                by1 = y1 - inset - 2
                img[by0:by1, bx0:bx1] = (255, 255, 255)
                img[by0:by1, bx0 : bx0 + 1] = 0
                img[by0:by1, bx1 - 1 : bx1] = 0
                img[by0 : by0 + 1, bx0:bx1] = 0
                img[by1 - 1 : by1, bx0:bx1] = 0
                _blit_text(
                    img,
                    ["OKAY.", "NEXT PANEL."],
                    x0=bx0 + 4,
                    y0=by0 + 4,
                    x1=bx1 - 4,
                    y1=by1 - 4,
                    color=(0, 0, 0),
                    scale=max(1, min(2, pw // 80)),
                )
    return img


def render_scan(w: int, h: int) -> np.ndarray:
    """Scanned book page: bookpage + grain + edge vignette."""
    img = render_bookpage(w, h).astype(np.float64)
    rng = _rng("scan", w, h)
    # Paper grain
    img += rng.normal(0.0, 6.0, size=img.shape)
    # Vignette (scanner falloff)
    yy = np.linspace(-1, 1, h).reshape(-1, 1)
    xx = np.linspace(-1, 1, w).reshape(1, -1)
    vig = 1.0 - 0.18 * (xx * xx + yy * yy)
    img *= vig[..., None]
    # Slight yellow channel bias
    img[:, :, 2] *= 0.97
    img[:, :, 0] *= 1.01
    return _to_u8(img)


def render_text(w: int, h: int) -> np.ndarray:
    """Black-on-white UI/screenshot text (hard edges, flat runs)."""
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    margin = max(16, min(w, h) // 20)
    lines = [
        "BENCHTOO — TEXT CLASS",
        "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG 0123456789",
        "HARD EDGES AND FLAT RUNS STRESS JPEG RINGING AND HUFFMAN",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        f"SIZE {w}X{h} DETERMINISTIC BITMAP FONT",
        "REPEATED LINE FOR VERTICAL COVERAGE " * 2,
        "PACKED ROWS: IIIILLLLOOOOMMMMNNNN / 1234567890",
        "SCREENSHOT-LIKE UI TEXT NOT BOOK PROSE",
        "END OF SAMPLE",
    ]
    scale = max(1, min(4, (w - 2 * margin) // (5 * 48)))
    _blit_text(
        img,
        lines,
        x0=margin,
        y0=margin,
        x1=w - margin,
        y1=h - margin,
        color=(0, 0, 0),
        scale=scale,
    )
    ry = margin + 7 * scale + max(2, scale * 2) // 2
    if 0 <= ry < h:
        img[ry : ry + max(1, scale // 2), margin : w - margin, :] = 40
    return img


def render_geometry(w: int, h: int) -> np.ndarray:
    """Shapes on a light field."""
    rng = _rng("geometry", w, h)
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

    cs = max(8, min(w, h) // 24)
    for iy in range(0, h // 3, cs):
        for ix in range(0, w // 3, cs):
            if ((ix // cs) + (iy // cs)) % 2 == 0:
                img[iy : iy + cs, ix : ix + cs] = (20, 20, 20)

    disk(int(w * 0.7), int(h * 0.35), min(w, h) // 6, (200, 40, 40), True)
    disk(
        int(w * 0.55),
        int(h * 0.55),
        min(w, h) // 8,
        (40, 40, 200),
        False,
        width=max(2, min(w, h) // 120),
    )
    disk(int(w * 0.3), int(h * 0.65), min(w, h) // 10, (40, 160, 60), True)
    rect(int(w * 0.1), int(h * 0.4), int(w * 0.35), int(h * 0.55), (180, 120, 20), True)
    rect(
        int(w * 0.65),
        int(h * 0.7),
        int(w * 0.9),
        int(h * 0.9),
        (30, 30, 30),
        False,
        width=max(2, min(w, h) // 100),
    )
    for t in range(0, max(w, h), max(2, min(w, h) // 200)):
        x = t
        y = t * h // max(w, 1)
        if 0 <= y < h and 0 <= x < w:
            img[y, max(0, x - 1) : min(w, x + 2)] = (0, 0, 0)
        x2 = w - 1 - t
        y2 = t * h // max(w, 1)
        if 0 <= y2 < h and 0 <= x2 < w:
            img[y2, max(0, x2 - 1) : min(w, x2 + 2)] = (80, 0, 80)

    for _ in range(12):
        bw = int(rng.integers(w // 40, max(w // 40 + 1, w // 15)))
        bh = int(rng.integers(h // 40, max(h // 40 + 1, h // 15)))
        x0 = int(rng.integers(0, max(1, w - bw)))
        y0 = int(rng.integers(0, max(1, h - bh)))
        color = tuple(int(c) for c in rng.integers(0, 255, size=3))
        img[y0 : y0 + bh, x0 : x0 + bw] = color
    return _to_u8(img)


def render_fractal(w: int, h: int) -> np.ndarray:
    """Mandelbrot — detail at all scales."""
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
    r = _to_u8(9 * (1 - t) * t * t * t * 255)
    g = _to_u8(15 * (1 - t) * (1 - t) * t * t * 255)
    b = _to_u8(8.5 * (1 - t) * (1 - t) * (1 - t) * t * 255)
    interior = esc == max_iter
    r[interior] = 0
    g[interior] = 0
    b[interior] = 0
    return np.stack([r, g, b], axis=2)


def render_noise(w: int, h: int) -> np.ndarray:
    rng = _rng("noise", w, h)
    return rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)


def render_mixed(w: int, h: int) -> np.ndarray:
    """Gallery-style composite (landscape-friendly)."""
    img = np.full((h, w, 3), 245, dtype=np.uint8)
    hh = max(h // 8, 24)
    for y in range(hh):
        t = y / max(hh - 1, 1)
        img[y, :] = (int(30 + 40 * t), int(60 + 80 * t), int(120 + 100 * t))
    panel = render_photo(w // 2, h - hh)
    img[hh:h, w // 2 : w // 2 + panel.shape[1]] = panel[:, : w - w // 2]
    geo_h = (h - hh) // 2
    geo = render_geometry(w // 2, geo_h)
    img[hh + (h - hh) // 2 : hh + (h - hh) // 2 + geo_h, 0 : w // 2] = geo[:, : w // 2]
    text_h = (h - hh) // 2
    text = render_text(w // 2, text_h)
    img[hh : hh + text_h, 0 : w // 2] = text[:, : w // 2]
    img[hh : hh + 2, :] = 20
    img[hh:, w // 2 : w // 2 + 2] = 20
    return img


# aspect: which size list; large_index is the last entry dropped by --no-large
CLASSES: dict[str, dict] = {
    "photo": {
        "fn": render_photo,
        "aspect": "landscape",
        "intent": "camera-like multi-octave noise; general JPEG path",
    },
    "landscape": {
        "fn": render_landscape,
        "aspect": "landscape",
        "intent": "wide scenic sky/horizon/terrain; landscape album images",
    },
    "bookpage": {
        "fn": render_bookpage,
        "aspect": "portrait",
        "intent": "portrait ebook page: cream paper, dense text, page number",
    },
    "spread": {
        "fn": render_spread,
        "aspect": "landscape",
        "intent": "two-page open book with gutter; landscape spreads",
    },
    "comic": {
        "fn": render_comic,
        "aspect": "portrait",
        "intent": "comic/manga panel grid, gutters, speech boxes",
    },
    "scan": {
        "fn": render_scan,
        "aspect": "portrait",
        "intent": "scanned book page: grain + vignette on bookpage",
    },
    "text": {
        "fn": render_text,
        "aspect": "landscape",
        "intent": "black-on-white UI text; hard edges and flat runs",
    },
    "geometry": {
        "fn": render_geometry,
        "aspect": "landscape",
        "intent": "circles/rects/checker; flats and hard edges",
    },
    "fractal": {
        "fn": render_fractal,
        "aspect": "landscape",
        "intent": "Mandelbrot; detail at all scales for shrink vs full",
    },
    "noise": {
        "fn": render_noise,
        "aspect": "landscape",
        "intent": "full-entropy noise; encode/decode upper bound",
    },
    "mixed": {
        "fn": render_mixed,
        "aspect": "landscape",
        "intent": "gallery composite: header + text + geometry + photo",
    },
}


def _label_banner(img: np.ndarray, class_name: str, intent: str) -> np.ndarray:
    """Burn class, resolution, and purpose into the image so fixtures are self-explanatory."""
    h, w = img.shape[:2]
    out = img.copy()
    banner_h = max(28, min(h // 18, 56))
    # Dark bar at bottom
    y0 = h - banner_h
    out[y0:h, :, :] = (20, 20, 24)
    # Thin accent line
    out[max(0, y0 - 2) : y0, :, :] = (80, 140, 220)
    scale = max(1, min(3, banner_h // 14))
    lines = [
        f"{class_name.upper()}  {w}X{h}  BENCHTOO",
        intent.upper()[: max(20, w // (5 * scale + 1))],
    ]
    _blit_text(
        out,
        lines,
        x0=max(4, w // 80),
        y0=y0 + max(2, banner_h // 10),
        x1=w - 4,
        y1=h - 2,
        color=(230, 230, 235),
        scale=scale,
        line_gap=max(1, scale),
    )
    return out



def save_png(rgb: np.ndarray, path: Path) -> None:
    Image.fromarray(np.ascontiguousarray(rgb), mode="RGB").save(
        path, format="PNG", optimize=False
    )


def save_jpeg(rgb: np.ndarray, path: Path, quality: int) -> None:
    Image.fromarray(np.ascontiguousarray(rgb), mode="RGB").save(
        path, format="JPEG", quality=quality, optimize=False, subsampling=0
    )


def _sizes_for(aspect: str, no_large: bool, with_8k: bool) -> list[tuple[int, int]]:
    if aspect == "portrait":
        sizes = list(SIZES_PORTRAIT)
    else:
        sizes = list(SIZES_LANDSCAPE)
    if no_large and len(sizes) >= 2:
        sizes = sizes[:-1]
    if with_8k and aspect == "landscape":
        sizes.append((7680, 4320))
    return sizes


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
        help="omit largest size in each aspect set (faster smoke)",
    )
    ap.add_argument(
        "--with-8k",
        action="store_true",
        help="also generate 7680×4320 for landscape-aspect classes",
    )
    args = ap.parse_args()

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
        sizes = _sizes_for(meta["aspect"], args.no_large, args.with_8k)
        for w, h in sizes:
            rgb = meta["fn"](w, h)
            if rgb.shape != (h, w, 3):
                raise RuntimeError(f"{cls} produced {rgb.shape}, expected {(h, w, 3)}")
            rgb = _label_banner(rgb, cls, meta["intent"])
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
                        "aspect": meta["aspect"],
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
                f"wrote {jpg_path.name} ({w}x{h}, {mpix:.2f} MP, jpeg={jpg_bytes} B) "
                f"— {meta['intent']}",
                file=sys.stderr,
            )

    manifest = {
        "schema": 3,
        "generator": "gen_synthetic.py",
        "generator_note": (
            "content-class matrix with landscape + portrait aspects "
            "(ebook/comic/photo oriented)"
        ),
        "entries": entries,
    }
    man_path = root / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest entries={len(entries)} -> {man_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
