#!/usr/bin/env python3
"""Hitung ulang rezim untuk 2008, 2009, 2020, dan 2022, lalu bandingkan
dengan yang akan disebut seorang analis untuk periode itu.

Syarat "selesai" pertama Fase 4 di docs/04-roadmap.md. Harapannya ditulis
lebih dulu di roadmap, bukan dikarang setelah melihat hasilnya — itu bedanya
menguji dari mencocokkan:

- risk-off di Q4 2008
- momentum-crash guard aktif Apr–Sep 2009
- guard aktif lagi Apr–Sep 2020
- risk-off sebagian besar 2022

Butuh jaringan: ^GSPC dan ^VIX sejak 2007 dari Yahoo.

    python scripts/uji_rezim_historis.py
    python scripts/uji_rezim_historis.py --csv-keluaran hasil/rezim_historis.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import makro  # noqa: E402

# Harapan per periode: (mulai, selesai, rezim yang diharapkan, keterangan).
# "guard" berarti cukup guard aktif; rezim lain dicocokkan persis.
HARAPAN = [
    ("2008-10-01", "2008-12-31", makro.RISK_OFF, "Krisis keuangan, Q4 2008"),
    ("2009-04-01", "2009-09-30", makro.GUARD, "Pantulan pertama setelah Maret 2009"),
    ("2020-04-01", "2020-09-30", makro.GUARD, "Pantulan setelah crash Covid"),
    ("2022-01-01", "2022-12-31", makro.RISK_OFF, "Pengetatan Fed sepanjang 2022"),
]
# 2022 tidak risk-off tiap hari (ada reli beruang Juli–Agustus), jadi yang
# diminta "sebagian besar", bukan seluruhnya.
AMBANG_SEBAGIAN_BESAR = 0.60


def unduh(mulai: str) -> tuple[pd.Series, pd.Series]:
    import yfinance as yf

    data = yf.download(["^GSPC", "^VIX"], start=mulai, auto_adjust=False,
                       progress=False, group_by="ticker")
    # yfinance mengembalikan tabel kosong (bukan galat) ketika jaringannya
    # diblokir, jadi kekosongannya harus diperiksa sendiri — kalau tidak,
    # skrip ini mati dengan IndexError yang tidak menjelaskan apa pun.
    if data is None or data.empty:
        raise RuntimeError("Yahoo mengembalikan tabel kosong")
    spx = data["^GSPC"]["Close"].dropna()
    vix = data["^VIX"]["Close"].dropna()
    if spx.empty:
        raise RuntimeError("^GSPC kosong")
    return spx, vix


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mulai", default="2007-01-01", help="Awal histori (butuh ≥ 1 tahun sebelum periode pertama)")
    p.add_argument("--csv-keluaran", type=Path, help="Simpan rezim bulanan ke CSV")
    p.add_argument("--dari-csv", type=Path,
                   help="Baca ^GSPC/^VIX dari CSV berkolom Tanggal,SPX,VIX (untuk jalan tanpa jaringan)")
    a = p.parse_args(argv)

    if a.dari_csv:
        d = pd.read_csv(a.dari_csv, parse_dates=["Tanggal"]).set_index("Tanggal")
        spx, vix = d["SPX"].dropna(), d["VIX"].dropna()
    else:
        print(f"Mengunduh ^GSPC dan ^VIX sejak {a.mulai}…", file=sys.stderr)
        try:
            spx, vix = unduh(a.mulai)
        except Exception as e:
            print(f"Unduhan gagal ({type(e).__name__}: {e}). Butuh jaringan ke Yahoo, "
                  "atau pakai --dari-csv.", file=sys.stderr)
            return 2
    print(f"{len(spx)} hari SPX, {len(vix)} hari VIX, {spx.index[0].date()} – {spx.index[-1].date()}\n")

    # Rezim harian, bukan bulanan: "guard aktif Apr–Sep" adalah pernyataan
    # tentang rentang, dan rentang itu bisa terlewat oleh sampel akhir bulan.
    harian = makro.rezim_historis(spx, vix, tanggal=spx.index)
    if a.csv_keluaran:
        a.csv_keluaran.parent.mkdir(parents=True, exist_ok=True)
        harian.to_csv(a.csv_keluaran, index=False, encoding="utf-8")
        print(f"{len(harian)} baris → {a.csv_keluaran}\n")

    h = harian.set_index(pd.to_datetime(harian["Tanggal"]))
    baris, lolos_semua = [], True
    for mulai, selesai, diharap, catatan in HARAPAN:
        potong = h.loc[mulai:selesai]
        if potong.empty:
            baris.append({"Periode": f"{mulai} … {selesai}", "Harapan": diharap,
                          "Kenyataan": "tidak ada data", "Cocok_%": None, "Status": "?",
                          "Catatan": catatan})
            lolos_semua = False
            continue
        if diharap == makro.GUARD:
            cocok = potong["Guard"].astype(bool)
        else:
            cocok = potong["Rezim"] == diharap
        pct = 100.0 * cocok.mean()
        ok = pct >= AMBANG_SEBAGIAN_BESAR * 100
        lolos_semua &= ok
        terbanyak = potong["Rezim"].value_counts()
        baris.append({"Periode": f"{mulai} … {selesai}", "Harapan": diharap,
                      "Kenyataan": f"{terbanyak.index[0]} ({terbanyak.iloc[0]}/{len(potong)} hari)",
                      "Cocok_%": round(pct, 1), "Status": "✅" if ok else "❌",
                      "Catatan": catatan})

    hasil = pd.DataFrame(baris)
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(hasil.to_string(index=False))
    print(f"\nAmbang: rezim yang diharapkan berlaku ≥ {AMBANG_SEBAGIAN_BESAR * 100:.0f}% hari "
          "dalam periodenya.")
    print("LOLOS" if lolos_semua else
          "GAGAL: ada periode yang rezimnya tidak seperti yang akan disebut analis. "
          "Sesuaikan ambang di usmarket/makro.py, atau tulis alasan mengapa hitungannya "
          "yang benar dan harapannya yang keliru — jangan diam-diam menyesuaikan harapannya.")
    return 0 if lolos_semua else 1


if __name__ == "__main__":
    sys.exit(main())
