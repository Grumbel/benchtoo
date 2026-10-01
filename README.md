<!--
SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later
-->

# pixel-bench-corpus

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
# documents/sample_book.djvu  — only if pdf2djvu is available
```

Raster fixtures also carry a **bottom banner** with class, resolution, and purpose.

## Archives

After synthetics exist:

```bash
python3 generators/gen_archives.py --corpus ./out
# out/archives/book_pages.cbz  comic_pages.cbz  mixed_album.zip
```

ZIP **stored** (no deflate) so extract timing is not dominated by zlib.

## Build

```bash
nix build
python3 generators/gen_synthetic.py --out ./out
python3 generators/gen_synthetic.py --out ./out --no-large
python3 generators/gen_synthetic.py --out ./out --classes bookpage,comic,spread,landscape
```

## License

GPL-3.0-or-later for generators and this tree.
