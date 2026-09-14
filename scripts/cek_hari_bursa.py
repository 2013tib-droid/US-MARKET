#!/usr/bin/env python3
"""Tentukan apakah run malam perlu jalan. Ditulis dalam format GITHUB_OUTPUT:

    jalan=true|false

Run terjadwal hanya berguna bila hari ini (tanggal New York) ada sesi NYSE.
Cron GitHub tidak tahu libur bursa AS; tanpa pemeriksaan ini, run pada
Labor Day atau Thanksgiving menarik ulang data kemarin dan membuat commit
yang isinya sama dengan kemarin.

Run manual (workflow_dispatch) dan run karena push selalu jalan: tujuannya
memang menguji kode, bukan mengambil data baru.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import kalender  # noqa: E402


def main() -> int:
    peristiwa = os.environ.get("GITHUB_EVENT_NAME", "")
    hari = kalender.tanggal_et()
    buka = kalender.adalah_hari_bursa(hari)
    jalan = buka or peristiwa != "schedule"
    alasan = (f"{hari} {'ada sesi NYSE' if buka else 'libur NYSE'}; "
              f"pemicu {peristiwa or 'lokal'} → {'jalan' if jalan else 'lewati'}")
    print(alasan, file=sys.stderr)
    print(f"jalan={'true' if jalan else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
