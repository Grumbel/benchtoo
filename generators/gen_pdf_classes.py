#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate PDF pages for each page-content class thumtoo tells apart.

thumtoo classifies every PDF page by what it draws (PdfPageProfile):

  empty   nothing visible
  vector  paths / glyphs, no images             -> rendered at any zoom
  raster  images only (scans)                   -> capped at native dpi
  mixed   images + visible vector or glyphs     -> rendered at any zoom

Invisible OCR text and a page-size background fill do not count as vector
detail. This generator writes one PDF per case at real page sizes and
resolutions (Letter / A4 / A2 at 150-600 dpi) plus ``pdf_classes.json`` with
the expected classification, so ``check_pdf_classes.py`` can verify thumtoo
(and biltoo's Status panel can be eyeballed against known answers).

Usage:
  python3 generators/gen_pdf_classes.py --out ./out
  python3 generators/gen_pdf_classes.py --out ./out --small   # quick, low dpi

Requires: reportlab, Pillow.
"""

from __future__ import annotations

import argparse
import io
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A2, A4, LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

LAYOUT_DPI = 144  # thumtoo kPdfLayoutDpi
DPI_TOLERANCE = 1.25  # thumtoo kPdfNativeDpiTolerance


def finest_useful_scale(native_dpi: float) -> int:
    """Mirror of thumtoo's cap: coarsest scale reaching native/tolerance, <= 0."""
    want = native_dpi / DPI_TOLERANCE
    return min(0, math.floor(math.log2(LAYOUT_DPI / want)))


# --- raster content ----------------------------------------------------------

def _font(px: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=px)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def scan_image(w_in: float, h_in: float, dpi: int, mode: str = "L",
               label: str = "") -> Image.Image:
    """A scanned text page: paper tone, ruled text lines, a margin note."""
    w, h = round(w_in * dpi), round(h_in * dpi)
    bg = {"L": 236, "RGB": (240, 234, 220), "1": 1}[mode]
    ink = {"L": 30, "RGB": (35, 30, 25), "1": 0}[mode]
    img = Image.new(mode, (w, h), bg)
    d = ImageDraw.Draw(img)
    font = _font(max(8, dpi // 8))
    line_h = max(10, dpi // 5)
    margin = dpi // 2
    words = ("thumtoo renders scanned pages at their native resolution and "
             "vector pages at any zoom level ").split()
    y = margin
    n = 0
    while y < h - margin:
        x = margin
        while x < w - margin:
            word = words[n % len(words)]
            n += 1
            d.text((x, y), word, fill=ink, font=font)
            x += int(font.getlength(word)) + dpi // 10
        y += line_h
    if label:
        d.text((margin, h - margin // 2 - dpi // 8), label, fill=ink, font=_font(dpi // 6))
    return img


def photo_image(w: int, h: int) -> Image.Image:
    """Smooth colour gradients with a horizon, like a photograph."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = y / max(1, h - 1)
            s = x / max(1, w - 1)
            if t < 0.55:
                px[x, y] = (int(90 + 100 * t), int(140 + 80 * t), int(230 - 40 * s))
            else:
                px[x, y] = (int(60 + 60 * s), int(120 - 50 * (t - 0.55)), 50)
    return img


def reader(img: Image.Image, jpeg: bool) -> ImageReader:
    """JPEG bytes (embedded as DCT) or the PIL image (embedded as Flate)."""
    if not jpeg:
        return ImageReader(img)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    buf.seek(0)
    return ImageReader(buf)


# --- vector content ----------------------------------------------------------

def body_text(c: canvas.Canvas, x: float, y: float, width: float, lines: int,
              size: float = 10.0) -> None:
    text = c.beginText(x, y)
    text.setFont("Helvetica", size)
    sentence = ("Vector text stays sharp at every zoom level; thumtoo never caps "
                "pages that draw glyphs or paths. ")
    per_line = max(10, int(width / (size * 0.5)))
    for i in range(lines):
        text.textLine((sentence * 3)[i % 17: i % 17 + per_line])
    c.drawText(text)


def invisible_text(c: canvas.Canvas, x: float, y: float, lines: int) -> None:
    text = c.beginText(x, y)
    text.setFont("Helvetica", 10)
    text.setTextRenderMode(3)  # invisible: an OCR layer
    for i in range(lines):
        text.textLine(f"OCR layer line {i} recognised words for search")
    c.drawText(text)


# --- cases -----------------------------------------------------------------

@dataclass
class Case:
    name: str
    kind: str
    page_size: tuple[float, float]
    draw: Callable[[canvas.Canvas, "Case", bool], None]
    native_dpi: float = 0.0
    background_fill_ignored: bool = False
    invisible_text: bool = False
    rotate: int = 0
    note: str = ""

    def expect(self) -> dict:
        exp = {
            "kind": self.kind,
            "native_dpi": self.native_dpi,
            "finest_useful_scale": (finest_useful_scale(self.native_dpi)
                                    if self.kind == "raster" else None),
            "background_fill_ignored": self.background_fill_ignored,
            "invisible_text": self.invisible_text,
        }
        return exp


def full_page(c: canvas.Canvas, img: Image.Image, jpeg: bool, case: Case) -> None:
    w, h = case.page_size
    c.drawImage(reader(img, jpeg), 0, 0, width=w, height=h)


def dpi_for(case: Case, small: bool) -> int:
    return int(case.native_dpi // 4) if small else int(case.native_dpi)


def make_cases(small: bool) -> list[Case]:
    def scale(dpi: float) -> float:
        return dpi / 4 if small else dpi

    cases: list[Case] = []

    def add(**kw):
        cases.append(Case(**kw))

    def scan_draw(mode="L", jpeg=True, label="", extra=None, bg_fill=False):
        def draw(c, case, small_):
            w, h = case.page_size
            if bg_fill:
                c.setFillColorRGB(1, 1, 1)
                c.rect(0, 0, w, h, fill=1, stroke=0)
            img = scan_image(w / 72, h / 72, dpi_for(case, small_), mode, label or case.name)
            full_page(c, img, jpeg and mode != "1", case)
            if extra:
                extra(c, case)
        return draw

    add(name="empty", kind="empty", page_size=LETTER, draw=lambda c, case, s: None,
        note="blank page")
    add(name="vector-text", kind="vector", page_size=LETTER,
        draw=lambda c, case, s: body_text(c, 72, 720, 468, 50),
        note="born-digital text page")

    def diagram(c, case, s):
        c.setLineWidth(1.5)
        for i in range(12):
            c.circle(306, 396, 20 + i * 18)
        for i in range(0, 612, 36):
            c.line(i, 0, 612 - i, 792)
        c.setFont("Helvetica", 9)
        c.drawString(60, 60, "Fig. 1")
    add(name="vector-diagram", kind="vector", page_size=LETTER, draw=diagram,
        note="lines and circles, three glyphs (old heuristic called this a scan)")

    add(name="scan-gray-300", kind="raster", page_size=LETTER, native_dpi=scale(300),
        draw=scan_draw(), note="greyscale JPEG scan")
    add(name="scan-rgb-600-a4", kind="raster", page_size=A4, native_dpi=scale(600),
        draw=scan_draw("RGB"), note="colour JPEG scan, 600 dpi")
    add(name="scan-ocr-300", kind="raster", page_size=LETTER, native_dpi=scale(300),
        invisible_text=True,
        draw=scan_draw(extra=lambda c, case: invisible_text(c, 72, 720, 40)),
        note="searchable scan: invisible OCR text over the image")
    add(name="scan-white-background-300", kind="raster", page_size=LETTER,
        native_dpi=scale(300), background_fill_ignored=True,
        draw=scan_draw(bg_fill=True), note="white page fill, then the scan")
    add(name="scan-bitonal-400", kind="raster", page_size=LETTER, native_dpi=scale(400),
        draw=scan_draw("1", jpeg=False), note="1-bit scan (Flate)")

    def mixed_raster(c, case, s):
        w, h = case.page_size
        bg = photo_image(round(w / 72 * scale(150)), round(h / 72 * scale(150)))
        c.drawImage(reader(bg, True), 0, 0, width=w, height=h)
        fg = scan_image(w / 72, h / 72, int(scale(600)), "L", case.name)
        # colour-key white as transparent: a sharp text layer over a soft background
        c.drawImage(ImageReader(fg), 0, 0, width=w, height=h, mask=[200, 255])
    add(name="mixed-raster-150-600", kind="raster", page_size=LETTER,
        native_dpi=scale(600), draw=mixed_raster,
        note="MRC-style: 150 dpi colour background + 600 dpi text layer; cap follows the sharpest")

    def bates(c, case):
        c.setFont("Helvetica-Bold", 8)
        c.drawString(470, 20, "DEF-000123")
        c.drawString(40, 20, "CONFIDENTIAL")
    add(name="scan-bates-stamp", kind="mixed", page_size=LETTER, native_dpi=scale(300),
        draw=scan_draw(extra=bates), note="scan + Bates number / stamp as vector text")

    def clearscan(c, case, s):
        w, h = case.page_size
        bg = photo_image(round(w / 72 * scale(150)), round(h / 72 * scale(150)))
        c.drawImage(reader(bg, True), 0, 0, width=w, height=h)
        body_text(c, 72, 720, 468, 45)
    add(name="clearscan", kind="mixed", page_size=LETTER, native_dpi=scale(150),
        draw=clearscan, note="background image + visible recognised glyphs")

    def magazine(c, case, s):
        img = photo_image(round(4 * scale(200)), round(3 * scale(200)))
        c.drawImage(reader(img, True), 72, 450, width=288, height=216)
        body_text(c, 72, 420, 220, 28, 9)
        body_text(c, 320, 720, 220, 55, 9)
    add(name="magazine", kind="mixed", page_size=LETTER, native_dpi=scale(200),
        draw=magazine, note="photo placed in a text layout")

    def a2_map(c, case, s):
        w, h = case.page_size
        c.setLineWidth(0.2)
        for i in range(0, int(w), 6):
            c.line(i, 0, i + 200, h)
        c.setFont("Helvetica", 4)
        for y in range(40, int(h), 40):
            c.drawString(40, y, f"grid row {y} — tiny labels need deep zoom")
    add(name="vector-a2-map", kind="vector", page_size=A2, draw=a2_map,
        note="large vector page: deep zoom far beyond the old 100 MP limit")

    add(name="scan-rotated-300", kind="raster", page_size=LETTER, native_dpi=scale(300),
        rotate=90, draw=scan_draw(), note="/Rotate 90")
    return cases


def write_case(out: Path, case: Case, small: bool) -> None:
    c = canvas.Canvas(str(out), pagesize=case.page_size)
    c.setTitle(f"benchtoo pdf class: {case.name}")
    if case.rotate:
        c.setPageRotation(case.rotate)
    case.draw(c, case, small)
    c.showPage()
    c.save()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--small", action="store_true",
                    help="quarter resolution images (fast; CI)")
    args = ap.parse_args()
    dest = args.out / "pdf-classes"
    dest.mkdir(parents=True, exist_ok=True)
    entries = []
    for case in make_cases(args.small):
        path = dest / f"{case.name}.pdf"
        write_case(path, case, args.small)
        entries.append({
            "file": f"pdf-classes/{path.name}",
            "page": 1,
            "note": case.note,
            "expect": case.expect(),
        })
        print(f"wrote {path} ({path.stat().st_size // 1024} KiB)")
    manifest = {
        "schema": 1,
        "generator": "gen_pdf_classes.py",
        "layout_dpi": LAYOUT_DPI,
        "dpi_tolerance": DPI_TOLERANCE,
        "small": args.small,
        "entries": entries,
    }
    (args.out / "pdf_classes.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {args.out / 'pdf_classes.json'} ({len(entries)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
