<!--
SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later
-->

# benchtoo

## Repository

https://github.com/Grumbel/benchtoo

```bash
git clone https://github.com/Grumbel/benchtoo.git
nix build
python3 generators/gen_synthetic.py --out ./out --no-large
```


Versioned image fixtures for **thumtoo** / **biltoo** pixel benchmarks.
Biltoo is largely an **ebook / comic / album** viewer — the matrix includes
portrait pages, landscape photos, spreads, and comic panels on purpose.

## Content classes

| Class | Aspect | Content | Stresses |
|-------|--------|---------|----------|
| **photo** | landscape | Multi-octave noise + colour washes | Typical camera JPEG |
| **landscape** | landscape | Sky, sun, horizon, terrain | Wide album photos |
| **bookpage** | portrait | Cream paper, dense body text, page № | Ebook single pages |
| **spread** | landscape | Two pages + centre gutter | Open-book spreads |
| **comic** | portrait | Panel grid, gutters, speech boxes | Manga/comic pages |
| **scan** | portrait | Bookpage + grain + vignette | Scanned paper |
| **text** | landscape | Black-on-white UI text | Hard edges / JPEG ringing |
| **geometry** | landscape | Shapes + checker | Flats + edges |
| **fractal** | landscape | Mandelbrot | Detail at all scales |
| **noise** | landscape | Full-entropy noise | Encode/decode upper bound |
| **mixed** | landscape | Header + text + geometry + photo | Gallery composite |

### Size sets

- **Landscape (16:9):** 800×450, 1920×1080, 3840×2160
- **Portrait (~2:3):** 600×900, 1200×1800, 1600×2400

`--no-large` drops the largest size in each set. `--with-8k` adds 7680×4320
for landscape classes only.

## Documents (PDF, text, Markdown)

```bash
python3 generators/gen_documents.py --out ./out --pages 40
# documents/sample_book.pdf   — multi-page A4 book (chapters, figures, footers)
# documents/sample_article.md
# documents/sample_notes.txt
# documents/sample_book.cbz   — rasterized pages (needs pdftoppm)
# documents/sample_book.djvu  — only if pdf2djvu is on PATH (not in nixpkgs)
```

Raster fixtures also carry a **bottom banner** with class, resolution, and purpose.

## PDF page classes

```bash
python3 generators/gen_pdf_classes.py --out ./out          # full resolution
python3 generators/gen_pdf_classes.py --out ./out --small  # quarter dpi (CI)
(cd generators && python3 gen_djvu_classes.py --out ../out)   # needs djvulibre
python3 generators/check_page_classes.py --corpus ./out \
    --tool /path/to/thumtoo-page-profile --render --threads 4
```

One PDF per page-content class thumtoo distinguishes (`PdfPageProfile`):
empty, vector text, vector diagram, large vector map (A2), greyscale / colour /
bitonal scans at 300–600 dpi, a searchable scan (invisible OCR text), a scan
with a white background fill, an MRC-style 150 + 600 dpi scan, a scan with a
Bates stamp, ClearScan-style (image + visible glyphs), a magazine page and a
rotated scan. `out/pdf_classes.json` holds the expected kind, native dpi,
resolution cap and flags; `check_page_classes.py` compares thumtoo's verdict
and, with `--render`, checks that each image decodes once per page and zoom
level.

DjVu: `gen_djvu_classes.py` writes bitonal (300/600 dpi), photo (150 dpi),
compound (300 dpi JB2 + 100 dpi IW44), searchable (hidden text) and blank
pages, plus a bundled 6-page book, with `out/djvu_classes.json`
(layers, dpi, text layer). The checker reads both manifests.

## Archives

After synthetics exist:

```bash
python3 generators/gen_archives.py --corpus ./out
# out/archives/book_pages.cbz  comic_pages.cbz  mixed_album.zip
```

ZIP **stored** (no deflate) so extract timing is not dominated by zlib.

## Packages

| Attr | Contents |
|------|----------|
| `corpus` (default) | Full class matrix + large sizes + 40-page PDF + PDF page classes |
| `corpus-smoke` | `--no-large` photo/bookpage/comic + 8-page PDF + `--small` PDF classes (CI / flake check) |

```bash
nix build .#corpus-smoke
```

Optional RAR4 (when `rar` is installed): `python3 generators/gen_rar.py --corpus ./out`

## Build

```bash
nix build
python3 generators/gen_synthetic.py --out ./out
python3 generators/gen_synthetic.py --out ./out --no-large
python3 generators/gen_synthetic.py --out ./out --classes bookpage,comic,spread,landscape
```

## License

GPL-3.0-or-later for generators and this tree.
