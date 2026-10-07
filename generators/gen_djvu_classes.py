#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate DjVu pages for each kind of page thumtoo's DjVu backend profiles.

thumtoo reports DjVu pages as rasters at their native pixels (finest useful
scale 0), listing the JB2 mask / IW44 layers with their dpi and the size of
the hidden text layer; pages without image layers are empty.

  djvu-bitonal-300   JB2 text page, Letter, 300 dpi
  djvu-bitonal-600   JB2 text page, Letter, 600 dpi (8.4 -> 33.7 MP)
  djvu-photo-150     IW44 colour photo page, 150 dpi
  djvu-compound-300  JB2 300 dpi mask + 100 dpi IW44 background (typical book scan)
  djvu-ocr-300       bitonal page + hidden text layer (searchable scan)
  djvu-blank         INFO chunk only (blank page in a scanned book)
  djvu-book          bundled multi-page document of the pages above

Writes out/djvu-classes/*.djvu and out/djvu_classes.json (expectations), used by
check_page_classes.py.

Usage:
  python3 generators/gen_djvu_classes.py --out ./out [--small]

Requires: Pillow, djvulibre tools (c44, cjb2, djvumake, djvuextract, djvused,
djvm) on PATH — all in `nix develop`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from gen_pdf_classes import photo_image, scan_image

LETTER_IN = (8.5, 11.0)


def run(*cmd: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{' '.join(cmd)} failed:\n{proc.stderr}")


def bitonal(work: Path, name: str, dpi: int, small: bool) -> Path:
    dpi = dpi // 4 if small else dpi
    img = scan_image(*LETTER_IN, dpi, "1", name)
    pbm = work / f"{name}.pbm"
    img.save(pbm)
    out = work / f"{name}.djvu"
    run("cjb2", "-dpi", str(dpi), str(pbm), str(out))
    return out


def photo(work: Path, name: str, dpi: int, small: bool) -> Path:
    dpi = dpi // 4 if small else dpi
    img = photo_image(round(LETTER_IN[0] * dpi), round(LETTER_IN[1] * dpi))
    ppm = work / f"{name}.ppm"
    img.save(ppm)
    out = work / f"{name}.djvu"
    run("c44", "-dpi", str(dpi), str(ppm), str(out))
    return out


def compound(work: Path, name: str, small: bool) -> Path:
    mask = bitonal(work, name + "-mask", 300, small)
    bg = photo(work, name + "-bg", 100, small)
    run("djvuextract", str(mask), f"Sjbz={work / 'mask.jb2'}")
    run("djvuextract", str(bg), f"BG44={work / 'bg.iw44'}")
    dpi = 75 if small else 300
    w, h = round(LETTER_IN[0] * dpi), round(LETTER_IN[1] * dpi)
    out = work / f"{name}.djvu"
    run("djvumake", str(out), f"INFO={w},{h},{dpi}", f"Sjbz={work / 'mask.jb2'}",
        "FGbz=#202020", f"BG44={work / 'bg.iw44'}")
    return out


def ocr(work: Path, name: str, small: bool) -> Path:
    page = bitonal(work, name, 300, small)
    dpi = 75 if small else 300
    w, h = round(LETTER_IN[0] * dpi), round(LETTER_IN[1] * dpi)
    lines = []
    for i in range(20):
        y1 = h - 100 - i * (h // 25)
        lines.append(f'(line 100 {y1 - 40} {w - 100} {y1} '
                     f'(word 100 {y1 - 40} {w // 2} {y1} "recognised{i}") '
                     f'(word {w // 2 + 10} {y1 - 40} {w - 100} {y1} "words{i}"))')
    sexp = work / f"{name}.txt"
    sexp.write_text(f"(page 0 0 {w} {h} {' '.join(lines)})\n")
    run("djvused", str(page), "-e", f"select 1; set-txt {sexp}", "-s")
    return page


def blank(work: Path, name: str, small: bool) -> Path:
    dpi = 75 if small else 300
    w, h = round(LETTER_IN[0] * dpi), round(LETTER_IN[1] * dpi)
    out = work / f"{name}.djvu"
    # djvumake warns about a page without image chunks but writes it.
    subprocess.run(["djvumake", str(out), f"INFO={w},{h},{dpi}"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--small", action="store_true", help="quarter resolution (CI)")
    args = ap.parse_args()
    for tool in ("c44", "cjb2", "djvumake", "djvuextract", "djvused", "djvm"):
        if not shutil.which(tool):
            raise SystemExit(f"missing djvulibre tool: {tool}")
    dest = args.out / "djvu-classes"
    dest.mkdir(parents=True, exist_ok=True)
    q = 4 if args.small else 1

    def raster(dpi: int, layers: int, text: bool = False) -> dict:
        return {"kind": "raster", "native_dpi": dpi // q, "finest_useful_scale": 0,
                "layers": layers, "invisible_text": text,
                "background_fill_ignored": False}

    cases = [
        ("djvu-bitonal-300", lambda w: bitonal(w, "djvu-bitonal-300", 300, args.small),
         raster(300, 1), "JB2 text page"),
        ("djvu-bitonal-600", lambda w: bitonal(w, "djvu-bitonal-600", 600, args.small),
         raster(600, 1), "JB2 at 600 dpi: 4x the pixels of 300"),
        ("djvu-photo-150", lambda w: photo(w, "djvu-photo-150", 150, args.small),
         raster(150, 1), "IW44 colour page"),
        ("djvu-compound-300", lambda w: compound(w, "djvu-compound-300", args.small),
         raster(300, 2), "JB2 300 dpi mask + 100 dpi IW44 background"),
        ("djvu-ocr-300", lambda w: ocr(w, "djvu-ocr-300", args.small),
         raster(300, 1, text=True), "bitonal page with a hidden text layer"),
        ("djvu-blank", lambda w: blank(w, "djvu-blank", args.small),
         {"kind": "empty", "native_dpi": 300 // q, "finest_useful_scale": None,
          "layers": 0, "invisible_text": False, "background_fill_ignored": False},
         "INFO chunk only"),
    ]
    entries = []
    pages = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name, make, expect, note in cases:
            src = make(work)
            target = dest / f"{name}.djvu"
            shutil.copyfile(src, target)
            pages.append((src, expect, name))
            entries.append({"file": f"djvu-classes/{target.name}", "page": 1,
                            "note": note, "expect": expect})
            print(f"wrote {target} ({target.stat().st_size // 1024} KiB)")
        book = dest / "djvu-book.djvu"
        run("djvm", "-c", str(book), *[str(p[0]) for p in pages])
        for i, (_, expect, name) in enumerate(pages, start=1):
            entries.append({"file": f"djvu-classes/{book.name}", "page": i,
                            "note": f"bundled page {i} ({name})", "expect": expect})
        print(f"wrote {book} ({book.stat().st_size // 1024} KiB, {len(pages)} pages)")
    manifest = {"schema": 1, "generator": "gen_djvu_classes.py", "small": args.small,
                "entries": entries}
    (args.out / "djvu_classes.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {args.out / 'djvu_classes.json'} ({len(entries)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
