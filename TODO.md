<!--
SPDX-FileCopyrightText: 2026 Ingo Ruhnke <grumbel@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later
-->

# TODO / agent handoff

## Status (2026-10-07)

**Tip:** PDF page classes (Claude Code, direct commit)

### PDF page classes
- `generators/gen_pdf_classes.py` — 14 PDFs, one per thumtoo page-content
  class, with `out/pdf_classes.json` expectations (kind, native dpi, cap).
- `generators/check_pdf_classes.py` — runs `thumtoo-pdf-profile --json`
  (thumtoo ≥ f917301) and compares; `--render` checks decode-once.
- `devShells.default` with the Python environment (`nix develop`).
- Both corpus packages include the classes (`--small` for smoke).

Open: an annotation case (reportlab cannot draw annotation appearances;
thumtoo's own fixture test covers it), real-world sample PDFs (licensing).

### 009.1
- `packages.corpus-smoke` — photo/bookpage/comic, `--no-large`, 8-page PDF
- `packages.corpus` — full matrix
- `generators/gen_rar.py` — optional RAR4 when `rar` on PATH

### Repo
https://github.com/Grumbel/benchtoo
