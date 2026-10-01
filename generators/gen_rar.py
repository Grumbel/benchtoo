#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional RAR4 fixtures for unarr vs libarchive benches.

Requires the proprietary ``rar`` tool (RARLabs) on PATH. No-ops with exit 0
when missing so CI without rar still succeeds.

  python3 generators/gen_rar.py --corpus ./out

Writes archives/comic_sample.rar (RAR4, non-solid) and optionally
archives/comic_sample_solid.rar when source JPEGs exist.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, required=True)
    args = ap.parse_args()
    root: Path = args.corpus
    jpeg_dir = root / "synthetic" / "jpeg"
    if not jpeg_dir.is_dir():
        print("skip RAR: no synthetic/jpeg")
        return 0
    rar = shutil.which("rar")
    if not rar:
        print("skip RAR: rar(1) not on PATH")
        return 0

    sources = sorted(jpeg_dir.glob("comic_*_q90.jpg"))
    if not sources:
        sources = sorted(jpeg_dir.glob("*_q90.jpg"))[:3]
    if not sources:
        print("skip RAR: no jpeg sources")
        return 0

    out_dir = root / "archives"
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []

    with tempfile.TemporaryDirectory(prefix="benchtoo-rar-") as tmp:
        tmp_path = Path(tmp)
        for s in sources:
            shutil.copy2(s, tmp_path / s.name)

        # RAR4 non-solid
        out = out_dir / "comic_sample.rar"
        cmd = [rar, "a", "-m3", "-ma4", "-ep1", str(out), str(tmp_path / "*")]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"rar non-solid failed: {e}")
            return 0
        if out.is_file():
            print(f"wrote {out} bytes={out.stat().st_size}")
            entries.append(
                {
                    "id": "comic_sample_rar",
                    "path": str(out.relative_to(root)),
                    "class": "archive",
                    "codec": "rar4",
                    "intent": "RAR4 non-solid for unarr/libarchive A/B",
                    "license": "GPL-3.0-or-later",
                }
            )

        # RAR4 solid (interesting for unarr)
        out_s = out_dir / "comic_sample_solid.rar"
        cmd_s = [rar, "a", "-m3", "-ma4", "-s", "-ep1", str(out_s), str(tmp_path / "*")]
        try:
            subprocess.run(cmd_s, check=True, capture_output=True, timeout=120)
            if out_s.is_file():
                print(f"wrote {out_s} bytes={out_s.stat().st_size}")
                entries.append(
                    {
                        "id": "comic_sample_solid_rar",
                        "path": str(out_s.relative_to(root)),
                        "class": "archive",
                        "codec": "rar4-solid",
                        "intent": "RAR4 solid — unarr extract vs libarchive gap",
                        "license": "GPL-3.0-or-later",
                    }
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"rar solid failed (optional): {e}")

    man = root / "manifest.json"
    if man.is_file() and entries:
        data = json.loads(man.read_text(encoding="utf-8"))
        data.setdefault("entries", []).extend(entries)
        man.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
