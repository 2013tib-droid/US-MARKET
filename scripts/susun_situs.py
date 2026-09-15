#!/usr/bin/env python3
"""Bangkitkan halaman dokumen situs dari docs/*.md.

    python scripts/susun_situs.py [tujuan]     # bawaan: _site/docs

Dipanggil workflow screening malam sesudah dashboard dan hasil/ disalin ke
_site. Tidak menulis apa pun ke dalam repo: keluarannya hanya hidup di
artifact Pages, jadi dokumen sumbernya tetap satu-satunya yang di-commit.
"""

from __future__ import annotations

import sys
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))
from usmarket import situs  # noqa: E402


def main() -> int:
    tujuan = Path(sys.argv[1]) if len(sys.argv) > 1 else AKAR / "_site" / "docs"
    situs.bersihkan(tujuan)
    dokumen = situs.susun(AKAR / "docs", tujuan)
    print(f"{len(dokumen)} dokumen → {tujuan}", file=sys.stderr)
    for d in dokumen:
        print(f"  {d.slug}.html  {d.judul}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
