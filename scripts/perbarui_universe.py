#!/usr/bin/env python3
"""Perbarui daftar konstituen S&P 500/400/600 dan Nasdaq-100 dari Wikipedia.

Setiap indeks ditulis ke berkasnya sendiri di tickers/. Indeks yang gagal
diambil, atau tabelnya tidak wajar (jumlah baris di luar rentang, kolom
hilang), dilewati dan berkas lamanya dipertahankan. Skrip keluar dengan kode
1 hanya bila SEMUA indeks gagal, supaya satu halaman yang sedang diedit
tidak menggagalkan run malam.

    python scripts/perbarui_universe.py
    python scripts/perbarui_universe.py --indeks SP500 NDX
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import universe  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--indeks", nargs="+", choices=universe.URUTAN_INDEKS, default=universe.URUTAN_INDEKS)
    a = p.parse_args(argv)

    sesi = requests.Session()
    berhasil = 0
    for kode in a.indeks:
        path = universe.berkas_indeks(kode)
        try:
            df = universe.ambil_indeks(kode, sesi)
        except Exception as e:
            print(f"{kode}: GAGAL ({type(e).__name__}: {e}) — {path.name} lama dipertahankan", file=sys.stderr)
            continue
        lama = set()
        if path.exists():
            lama = set(pd.read_csv(path)["Ticker"])
        baru = set(df["Ticker"])
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8")
        berhasil += 1
        catatan = ""
        if lama:
            masuk, keluar = sorted(baru - lama), sorted(lama - baru)
            catatan = f"; masuk {masuk or '-'}, keluar {keluar or '-'}"
        print(f"{kode}: {len(df)} emiten → {path.relative_to(universe.AKAR)}{catatan}")

    total = len(universe.muat())
    print(f"Universe gabungan: {total} ticker unik")
    return 0 if berhasil else 1


if __name__ == "__main__":
    sys.exit(main())
