<!--
SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later
-->

# pixel-bench-corpus

Versioned image and archive fixtures for **thumtoo** / **biltoo** pixel
benchmarks. Kept out of the application source trees so binary samples stay
small in git and large assets are produced or pinned via Nix.

See thumtoo [`docs/BENCHMARK_KIT.md`](https://github.com/Grumbel/thumtoo/blob/master/docs/BENCHMARK_KIT.md).

## Build

```bash
nix build
# result/synthetic/jpeg/synth_1920x1080_q90.jpg
# result/manifest.json
```

Regenerate into a directory without a full store build:

```bash
nix run .#generate -- ./out
```

## Contents (v0.1)

| Path pattern | Purpose |
|--------------|---------|
| `synthetic/jpeg/synth_{W}x{H}_q90.jpg` | JPEG decode / shrink / tile encode scaling |
| `synthetic/png/synth_{W}x{H}.png` | Lossless reference for the same sizes |
| `manifest.json` | Machine-readable inventory |

Sizes: 800×600, 1920×1080, 3840×2160, 7680×4320 (3-band RGB uchar).

## Consume from thumtoo

```nix
# flake input
pixel-bench-corpus.url = "git+file:///path/to/pixel-bench-corpus";
# or github once published
```

```bash
export THUMTOO_BENCH_CORPUS=$(nix build --no-link --print-out-paths .#corpus)
thumtoo-microbench-decode "$THUMTOO_BENCH_CORPUS"/synthetic/jpeg/*.jpg
```

## License

GPL-3.0-or-later for generators and this tree. Public-domain pins (when added)
carry their own SPDX / source URL in `manifest.json`.
