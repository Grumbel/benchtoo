#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build ZIP/CBZ archives from already-generated synthetic JPEGs.

Produces random-access archive fixtures for thumtoo archive benches
(libarchive sequential vs scattered member extract).

Usage (after gen_synthetic.py):
  python3 generators/gen_archives.py --corpus ./out

Outputs under corpus/archives/:
  book_pages.cbz   — portrait bookpage JPEGs (sorted)
  comic_pages.cbz  — comic page JPEGs
  mixed_album.zip  — photo + landscape + spread (album-like)
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


def add_glob(zf: zipfile.ZipFile, jpeg_dir: Path, pattern: str, prefix: str) -> int:
    files = sorted(jpeg_dir.glob(pattern))
    for i, f in enumerate(files):
        arc = f"{prefix}/{i:03d}_{f.name}"
        zf.write(f, arcname=arc)
    return len(files)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, required=True, help="corpus root with synthetic/jpeg")
    args = ap.parse_args()
    root: Path = args.corpus
    jpeg_dir = root / "synthetic" / "jpeg"
    if not jpeg_dir.is_dir():
        raise SystemExit(f"missing {jpeg_dir} — run gen_synthetic.py first")

    out_dir = root / "archives"
    out_dir.mkdir(parents=True, exist_ok=True)

    specs = [
        ("book_pages.cbz", "bookpage_*_q90.jpg", "pages"),
        ("comic_pages.cbz", "comic_*_q90.jpg", "pages"),
        ("mixed_album.zip", "{photo,landscape,spread}_*_q90.jpg", "album"),
    ]

    manifest_extra = []
    for name, pattern, prefix in specs:
        path = out_dir / name
        # mixed uses multiple globs
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
            if "{" in pattern:
                n = 0
                for pat in ["photo_*_q90.jpg", "landscape_*_q90.jpg", "spread_*_q90.jpg"]:
                    n += add_glob(zf, jpeg_dir, pat, prefix)
            else:
                n = add_glob(zf, jpeg_dir, pattern, prefix)
        if n == 0:
            path.unlink(missing_ok=True)
            print(f"skip {name} (no matching JPEGs)")
            continue
        print(f"wrote {path} members={n} bytes={path.stat().st_size}")
        manifest_extra.append(
            {
                "id": path.stem,
                "path": str(path.relative_to(root)),
                "class": "archive",
                "codec": "zip-stored",
                "members": n,
                "intent": f"ZIP/CBZ fixture from {pattern}",
                "license": "GPL-3.0-or-later",
            }
        )

    man_path = root / "manifest.json"
    if man_path.is_file() and manifest_extra:
        data = json.loads(man_path.read_text(encoding="utf-8"))
        data.setdefault("entries", []).extend(manifest_extra)
        data["generator_note"] = (
            data.get("generator_note", "") + "; archives via gen_archives.py"
        ).strip("; ")
        man_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"updated {man_path} (+{len(manifest_extra)} archive entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
