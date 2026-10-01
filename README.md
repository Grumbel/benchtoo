<!--
SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later
-->

# pixel-bench-corpus

Versioned image fixtures for **thumtoo** / **biltoo** pixel benchmarks.
Kept out of application source trees so generators stay small in git and
assets are produced via Nix or `generators/gen_synthetic.py`.

See thumtoo [`docs/BENCHMARK_KIT.md`](https://github.com/Grumbel/thumtoo/blob/master/docs/BENCHMARK_KIT.md).

## Design: content classes (not solid fills)

Solid colour or single-ramp images are useless for JPEG/tile benches: they
compress to a few KB and barely exercise Huffman/IDCT or tile encode. This
corpus is a **matrix of content classes**, each aimed at a pipeline question:

| Class | Content | Stresses |
|-------|---------|----------|
| **photo** | Multi-octave value noise + colour washes + grain | Typical camera JPEG path |
| **text** | Black bitmap glyphs on white, rules | Hard edges, flat runs, JPEG ringing |
| **geometry** | Circles, rects, diagonals, checker | Flats + edges, tile boundaries |
| **fractal** | Mandelbrot escape colouring | Detail at every scale (shrink vs full) |
| **noise** | Full-entropy hash noise | Encode size / decode upper bound |
| **mixed** | Page layout: gradient + text + geometry + photo panel | Mixed document / gallery content |

Default sizes: **800×600** (smoke), **1920×1080** (primary), **3840×2160** (large).
8K is opt-in (`--with-8k`). Use `--no-large` for a fast smoke set.

All generators are seeded by `(class, width, height)` so output is deterministic
for a given generator version.

## Build

```bash
nix build
# result/synthetic/jpeg/photo_1920x1080_q90.jpg
# result/manifest.json
```

```bash
# local regenerate (needs numpy + Pillow)
python3 generators/gen_synthetic.py --out ./out
python3 generators/gen_synthetic.py --out ./out --no-large
python3 generators/gen_synthetic.py --out ./out --classes photo,text
```

## Example JPEG sizes (q90, 1920×1080, this generator)

| Class | Approx. bytes |
|-------|----------------|
| photo | ~440 KiB |
| text | ~210 KiB |
| geometry | ~160 KiB |
| fractal | ~310 KiB |
| noise | ~3.8 MiB |
| mixed | ~400 KiB |

(Previous solid-blue corpus was ~25 KiB at the same resolution — not useful.)

## License

GPL-3.0-or-later for generators and this tree. Public-domain pins (when added)
carry their own SPDX / source URL in `manifest.json`.
