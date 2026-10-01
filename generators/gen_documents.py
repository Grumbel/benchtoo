#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate non-pixel-primary fixtures for thumtoo: PDF, text, Markdown, optional DjVu.

Produces a small **sample book** (dozens of pages with chapters, figures, page
numbers) as a real multi-page PDF, plus plain text and Markdown for thumtoo's
document paths. Optionally raster page previews as JPEG for CBZ.

Usage:
  python3 generators/gen_documents.py --out ./out
  python3 generators/gen_documents.py --out ./out --pages 48

Requires: reportlab. Optional: Pillow (page JPEG previews), djvulibre tools for DjVu.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import zipfile
from pathlib import Path

from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4  # portrait book default


def _chapter_titles() -> list[str]:
    return [
        "Opening the Archive",
        "Tiles and Ladders",
        "Portrait Pages and Spreads",
        "Comics and Panel Grids",
        "Scans, Noise, and Entropy",
        "Formats Beyond Pixels",
        "A Note on Benchmarks",
        "Closing Remarks",
    ]


def _body_paragraphs(chapter_idx: int, page_in_chapter: int) -> list[str]:
    """Deterministic filler prose that still reads like a technical essay."""
    seeds = [
        (
            "Biltoo is, in large part, an ebook and comic reader as well as an "
            "image album viewer. Thumtoo sits underneath as a cache and index "
            "library: sizes, tiles, soft previews, and archive members."
        ),
        (
            "A portrait page is not the same workload as a landscape photograph. "
            "Hard edges from text, long flat runs of paper colour, and dense "
            "ink in comic panels stress JPEG and tile encode differently."
        ),
        (
            "This sample book exists so automated benches can open a multi-page "
            "PDF, walk page sizes, and request tiles without depending on a "
            "copyrighted title from the open web."
        ),
        (
            "Chapter {c} page {p} continues the argument: measure cold probe, "
            "shrink-on-load, full decode, and durable tiles on content that "
            "looks like what users actually open."
        ),
        (
            "Markdown and plain text paths matter too. Not every document is a "
            "raster. Thumtoo may surface text layers, outlines, or simple "
            "file-backed notes alongside pixel ladders."
        ),
        (
            "When comparing codecs or archive backends, keep the corpus fixed. "
            "Synthetic fixtures should be self-describing: resolution, class, "
            "and purpose visible on the page or in the file header."
        ),
    ]
    out = []
    for i, s in enumerate(seeds):
        out.append(s.format(c=chapter_idx + 1, p=page_in_chapter + 1))
        if i == 2:
            out.append(
                "Figure references on later pages are drawn as simple diagrams "
                "so the PDF is not an empty wall of prose."
            )
    return out


def _draw_header(c: canvas.Canvas, title: str, page_no: int, total: int) -> None:
    c.setFont("Times-Roman", 9)
    c.setFillColor(Color(0.35, 0.35, 0.4))
    c.drawString(20 * mm, PAGE_H - 12 * mm, "benchtoo — sample book")
    c.drawRightString(PAGE_W - 20 * mm, PAGE_H - 12 * mm, title[:48])
    c.setStrokeColor(Color(0.7, 0.7, 0.75))
    c.setLineWidth(0.4)
    c.line(20 * mm, PAGE_H - 14 * mm, PAGE_W - 20 * mm, PAGE_H - 14 * mm)


def _draw_footer(c: canvas.Canvas, page_no: int, total: int) -> None:
    c.setFont("Times-Roman", 9)
    c.setFillColor(Color(0.3, 0.3, 0.35))
    c.drawCentredString(PAGE_W / 2, 12 * mm, f"— {page_no} of {total} —")
    c.setFont("Courier", 7)
    c.drawString(20 * mm, 8 * mm, f"A4 portrait  purpose: multi-page PDF bench fixture")


def _draw_figure_diagram(c: canvas.Canvas, x: float, y: float, w: float, h: float, kind: int) -> None:
    """Simple vector figure so pages are not text-only."""
    c.setStrokeColor(Color(0.15, 0.15, 0.2))
    c.setFillColor(Color(0.93, 0.94, 0.96))
    c.rect(x, y, w, h, fill=1, stroke=1)
    c.setFont("Helvetica", 8)
    c.setFillColor(Color(0.2, 0.25, 0.35))
    if kind % 3 == 0:
        # Tile grid sketch
        c.drawString(x + 4, y + h - 12, "Figure: tile grid (schematic)")
        cols, rows = 4, 3
        gw, gh = (w - 16) / cols, (h - 28) / rows
        for r in range(rows):
            for col in range(cols):
                c.setFillColor(Color(0.55 + 0.08 * ((r + col) % 3), 0.65, 0.8))
                c.rect(x + 8 + col * gw, y + 8 + r * gh, gw - 2, gh - 2, fill=1, stroke=1)
    elif kind % 3 == 1:
        c.drawString(x + 4, y + h - 12, "Figure: ladder levels")
        for i, edge in enumerate((1.0, 0.7, 0.45, 0.25)):
            c.setFillColor(Color(0.3, 0.45 + 0.1 * i, 0.7))
            bw = w * edge * 0.85
            c.rect(x + (w - bw) / 2, y + 10 + i * (h - 30) / 4, bw, (h - 36) / 5, fill=1, stroke=1)
    else:
        c.drawString(x + 4, y + h - 12, "Figure: page vs spread")
        c.setFillColor(Color(0.95, 0.93, 0.88))
        c.rect(x + 10, y + 15, w * 0.35, h * 0.55, fill=1, stroke=1)
        c.rect(x + w * 0.48, y + 15, w * 0.22, h * 0.55, fill=1, stroke=1)
        c.rect(x + w * 0.72, y + 15, w * 0.22, h * 0.55, fill=1, stroke=1)
        c.setFont("Helvetica", 7)
        c.setFillColor(black)
        c.drawString(x + 14, y + 20, "page")
        c.drawString(x + w * 0.5, y + 20, "spread")


def write_sample_book_pdf(path: Path, num_pages: int) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    chapters = _chapter_titles()
    pages_per_chapter = max(2, num_pages // len(chapters))
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("benchtoo sample book")
    c.setAuthor("benchtoo")
    c.setSubject("Synthetic multi-page PDF for thumtoo/biltoo benches")

    page_no = 0
    # Title page
    page_no += 1
    c.setFont("Times-Bold", 22)
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2 + 40, "Sample Book")
    c.setFont("Times-Roman", 12)
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2 + 10, "benchtoo")
    c.setFont("Courier", 9)
    c.drawCentredString(
        PAGE_W / 2,
        PAGE_H / 2 - 20,
        f"Synthetic PDF fixture — {num_pages} pages — A4 portrait",
    )
    c.drawCentredString(
        PAGE_W / 2,
        PAGE_H / 2 - 36,
        "Purpose: multi-page PDF size probe, tiles, and TTFP benches",
    )
    _draw_footer(c, page_no, num_pages)
    c.showPage()

    # TOC
    page_no += 1
    _draw_header(c, "Contents", page_no, num_pages)
    c.setFont("Times-Bold", 16)
    c.drawString(20 * mm, PAGE_H - 30 * mm, "Contents")
    c.setFont("Times-Roman", 11)
    y = PAGE_H - 45 * mm
    for i, title in enumerate(chapters):
        c.drawString(25 * mm, y, f"{i + 1}.  {title}")
        y -= 8 * mm
        if y < 30 * mm:
            break
    _draw_footer(c, page_no, num_pages)
    c.showPage()

    while page_no < num_pages:
        ch = min((page_no - 2) // pages_per_chapter, len(chapters) - 1)
        page_in_ch = (page_no - 2) % pages_per_chapter
        page_no += 1
        title = chapters[ch]
        _draw_header(c, title, page_no, num_pages)

        if page_in_ch == 0:
            c.setFont("Times-Bold", 16)
            c.drawString(20 * mm, PAGE_H - 32 * mm, f"Chapter {ch + 1}")
            c.setFont("Times-Bold", 14)
            c.drawString(20 * mm, PAGE_H - 40 * mm, title)
            body_top = PAGE_H - 50 * mm
        else:
            body_top = PAGE_H - 28 * mm

        # Body text
        c.setFont("Times-Roman", 10)
        c.setFillColor(black)
        text = c.beginText(20 * mm, body_top)
        text.setLeading(14)
        width_chars = 88
        for para in _body_paragraphs(ch, page_in_ch):
            # naive wrap
            words = para.split()
            line = ""
            for w in words:
                trial = (line + " " + w).strip()
                if len(trial) > width_chars:
                    text.textLine(line)
                    line = w
                else:
                    line = trial
            if line:
                text.textLine(line)
            text.textLine("")
        c.drawText(text)

        # Figure on alternating chapter pages
        if page_in_ch == 1 or (page_no % 5 == 0):
            _draw_figure_diagram(
                c,
                25 * mm,
                30 * mm,
                PAGE_W - 50 * mm,
                55 * mm,
                page_no,
            )

        _draw_footer(c, page_no, num_pages)
        c.showPage()

    c.save()
    return {
        "id": "sample_book_pdf",
        "path": str(path.name) if False else None,  # filled by caller
        "pages": num_pages,
        "page_width_pt": PAGE_W,
        "page_height_pt": PAGE_H,
    }


def write_markdown(path: Path) -> None:
    path.write_text(
        """# benchtoo — sample Markdown

**Purpose:** exercise thumtoo / biltoo Markdown document paths (not only rasters).

## Why this file exists

Biltoo is partly an ebook reader. Markdown notes, READMEs, and exported text
should open without going through a full image ladder.

### Checklist for benches

1. Cold open and size/identity probe for `.md` files
2. Text extraction / layout if supported
3. Ensure pixel pipelines are not forced on pure text documents

```text
fixture: sample_article.md
resolution: n/a (text)
class: markdown
```

## Sample table

| Class     | Aspect    | Role                |
|-----------|-----------|---------------------|
| bookpage  | portrait  | ebook page raster   |
| spread    | landscape | two-page scan proxy |
| sample.pdf| portrait  | multi-page PDF      |

— end of sample Markdown —
""",
        encoding="utf-8",
    )


def write_plaintext(path: Path) -> None:
    path.write_text(
        """benchtoo sample plain text
====================================

Purpose: thumtoo text-file path (no raster decode).

This is a short plain-text fixture used by document benches. It is not an
image. If a viewer requests pixels for this path, that is a host policy
choice — the corpus marks it as class=text-document.

Lines for scrolling stress:
"""
        + "\n".join(f"  line {i:03d}: the quick brown fox jumps over the lazy dog" for i in range(1, 81))
        + "\n\n-- end of sample_notes.txt --\n",
        encoding="utf-8",
    )


def try_write_djvu_from_pdf(pdf: Path, djvu: Path) -> bool:
    """Best-effort DjVu via pdf2djvu or ImageMagick; skip if tools missing."""
    for cmd in (
        ["pdf2djvu", "-o", str(djvu), str(pdf)],
        ["ddjvu", "-format=pdf", str(pdf), str(djvu)],  # wrong direction; skip
    ):
        try:
            if cmd[0] == "ddjvu":
                continue
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            if djvu.is_file() and djvu.stat().st_size > 0:
                return True
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    # Optional: single-page via convert if available
    try:
        subprocess.run(
            ["convert", str(pdf) + "[0]", str(djvu.with_suffix(".tiff"))],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return False


def write_book_cbz_from_pdf(pdf: Path, cbz: Path, max_pages: int = 0) -> int:
    """Rasterize PDF pages with pdftoppm into a stored CBZ. Returns page count."""
    import tempfile
    import shutil

    if not pdf.is_file():
        return 0
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        print("skip book CBZ (pdftoppm not found)")
        return 0
    with tempfile.TemporaryDirectory(prefix="pbc-pdf-") as tmp:
        tmp_path = Path(tmp)
        prefix = tmp_path / "page"
        cmd = [pdftoppm, "-jpeg", "-r", "120", str(pdf), str(prefix)]
        if max_pages > 0:
            cmd = [pdftoppm, "-jpeg", "-r", "120", "-f", "1", "-l", str(max_pages), str(pdf), str(prefix)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"skip book CBZ (pdftoppm failed: {e})")
            return 0
        pages = sorted(tmp_path.glob("page*.jpg"))
        if not pages:
            print("skip book CBZ (no page images)")
            return 0
        cbz.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(cbz, "w", compression=zipfile.ZIP_STORED) as zf:
            for i, page in enumerate(pages):
                zf.write(page, arcname=f"pages/{i + 1:03d}.jpg")
        return len(pages)



def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True, help="corpus root")
    ap.add_argument("--pages", type=int, default=40, help="sample book page count (default 40)")
    ap.add_argument("--skip-djvu", action="store_true", help="do not attempt DjVu generation")
    args = ap.parse_args()
    root: Path = args.out
    doc = root / "documents"
    doc.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []

    pdf_path = doc / "sample_book.pdf"
    write_sample_book_pdf(pdf_path, max(8, args.pages))
    entries.append(
        {
            "id": "sample_book_pdf",
            "path": str(pdf_path.relative_to(root)),
            "class": "pdf-book",
            "codec": "pdf",
            "pages": max(8, args.pages),
            "aspect": "portrait",
            "intent": "multi-page A4 PDF book with chapters, figures, page numbers",
            "license": "GPL-3.0-or-later",
        }
    )
    print(f"wrote {pdf_path} pages={max(8, args.pages)}")

    cbz_path = doc / "sample_book.cbz"
    n_cbz = write_book_cbz_from_pdf(pdf_path, cbz_path)
    if n_cbz:
        entries.append(
            {
                "id": "sample_book_cbz",
                "path": str(cbz_path.relative_to(root)),
                "class": "cbz-book",
                "codec": "zip-stored",
                "pages": n_cbz,
                "aspect": "portrait",
                "intent": "CBZ of rasterized sample_book.pdf pages (pdftoppm)",
                "license": "GPL-3.0-or-later",
            }
        )
        print(f"wrote {cbz_path} pages={n_cbz}")

    md_path = doc / "sample_article.md"
    write_markdown(md_path)
    entries.append(
        {
            "id": "sample_article_md",
            "path": str(md_path.relative_to(root)),
            "class": "markdown",
            "codec": "text",
            "intent": "Markdown document path (non-raster)",
            "license": "GPL-3.0-or-later",
        }
    )
    print(f"wrote {md_path}")

    txt_path = doc / "sample_notes.txt"
    write_plaintext(txt_path)
    entries.append(
        {
            "id": "sample_notes_txt",
            "path": str(txt_path.relative_to(root)),
            "class": "text-document",
            "codec": "text",
            "intent": "plain text document path (non-raster)",
            "license": "GPL-3.0-or-later",
        }
    )
    print(f"wrote {txt_path}")

    djvu_path = doc / "sample_book.djvu"
    if not args.skip_djvu:
        if try_write_djvu_from_pdf(pdf_path, djvu_path):
            entries.append(
                {
                    "id": "sample_book_djvu",
                    "path": str(djvu_path.relative_to(root)),
                    "class": "djvu-book",
                    "codec": "djvu",
                    "intent": "DjVu multi-page (from sample PDF when tools allow)",
                    "license": "GPL-3.0-or-later",
                }
            )
            print(f"wrote {djvu_path}")
        else:
            print("skip DjVu (pdf2djvu / tools not available)")

    # Update or create manifest fragment
    man_path = root / "manifest.json"
    if man_path.is_file():
        data = json.loads(man_path.read_text(encoding="utf-8"))
        data.setdefault("entries", []).extend(entries)
        note = data.get("generator_note") or ""
        if "documents" not in note:
            data["generator_note"] = (note + "; documents via gen_documents.py").strip("; ")
        man_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"updated {man_path}")
    else:
        man_path.write_text(
            json.dumps(
                {
                    "schema": 3,
                    "generator": "gen_documents.py",
                    "entries": entries,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
