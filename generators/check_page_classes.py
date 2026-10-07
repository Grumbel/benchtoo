#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check thumtoo's page classification against the class generators.

Reads ``pdf_classes.json`` (gen_pdf_classes.py) and ``djvu_classes.json``
(gen_djvu_classes.py), whichever exist, runs ``thumtoo-page-profile --json``
on every case and
compares kind, native dpi, resolution cap, background-fill and OCR-layer
detection. With ``--render`` it also renders every cell at the page's cap
(or layout scale) and reports cells, time and exact image decode counts —
each image should decode once per page and zoom level, not once per cell.

Usage:
  python3 generators/check_page_classes.py --corpus ./out \\
      --tool /tmp/thumtoo-build/thumtoo-page-profile [--render] [--threads 4]

Exit status 1 when any case disagrees.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def profile(tool: str, pdf: Path, page: int, render: bool, threads: int) -> dict:
    cmd = [tool, "--json"]
    if render:
        cmd += ["--render", "cap", "--threads", str(threads)]
    cmd += [str(pdf), str(page)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if not proc.stdout.strip():
        return {"error": proc.stderr.strip() or f"exit {proc.returncode}"}
    data = json.loads(proc.stdout)
    return data["pages"][0]


def compare(expect: dict, got: dict) -> list[str]:
    if "error" in got:
        return [f"error: {got['error']}"]
    problems = []
    if got["kind"] != expect["kind"]:
        problems.append(f"kind {got['kind']} != {expect['kind']}")
    if abs(got["native_dpi"] - expect["native_dpi"]) > 1.0:
        problems.append(f"native_dpi {got['native_dpi']:.1f} != {expect['native_dpi']}")
    if got["finest_useful_scale"] != expect["finest_useful_scale"]:
        problems.append(f"finest_useful_scale {got['finest_useful_scale']} != "
                        f"{expect['finest_useful_scale']}")
    if "layers" in expect and len(got["images"]) != expect["layers"]:
        problems.append(f"{len(got['images'])} layers != {expect['layers']}")
    if got["background_fill_ignored"] != expect["background_fill_ignored"]:
        problems.append(f"background_fill_ignored {got['background_fill_ignored']}")
    if (got["invisible_glyphs"] > 0) != expect["invisible_text"]:
        problems.append(f"invisible_glyphs {got['invisible_glyphs']}")
    render = got.get("render")
    if render:
        if render["failed"]:
            problems.append(f"{render['failed']} cells failed: {render['first_error']}")
        images = max(1, got["image_draws"])
        if got["image_draws"] and render.get("decodes", 0) > images:
            problems.append(f"{render['decodes']} decodes for {got['image_draws']} "
                            f"image draws over {render['cells']} cells")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--tool", default="thumtoo-page-profile")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--threads", type=int, default=1)
    args = ap.parse_args()

    entries = []
    for name in ("pdf_classes.json", "djvu_classes.json"):
        path = args.corpus / name
        if path.exists():
            entries += json.loads(path.read_text())["entries"]
    if not entries:
        raise SystemExit(f"no *_classes.json in {args.corpus}")
    failures = 0
    for entry in entries:
        got = profile(args.tool, args.corpus / entry["file"], entry["page"],
                      args.render, args.threads)
        problems = compare(entry["expect"], got)
        status = "FAIL" if problems else "ok"
        failures += bool(problems)
        label = f"{Path(entry['file']).stem}:{entry['page']}"
        print(f"{status:4} {label:30} {got.get('summary', '')}")
        render = got.get("render")
        if render:
            print(f"     render s={render['scale']}: {render['cells']} cells "
                  f"{render['wall_ms']:.0f} ms, display lists "
                  f"{render.get('display_list_builds', '?')}, decodes "
                  f"{render.get('decodes', '?')} (full {render.get('full_decodes', '?')}, "
                  f"subarea {render.get('subarea_decodes', '?')})")
        for p in problems:
            print(f"     - {p}")
    print(f"{len(entries) - failures}/{len(entries)} cases agree")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
