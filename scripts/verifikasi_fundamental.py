#!/usr/bin/env python3
"""Cocokkan data/fundamental.csv dengan sumber independen (laporan keuangan
kuartalan di Yahoo Finance) untuk sampel acak emiten non-keuangan.

Ini bukan uji otomatis di CI — Yahoo sering lambat dan angkanya sendiri
kadang direvisi — melainkan alat audit yang dijalankan saat logika ekstraksi
berubah. Hanya periode yang sama yang dibandingkan: bila kuartal terakhir
Yahoo berbeda dari Periode_Lapkeu kita, emiten itu dilewati.

    python scripts/verifikasi_fundamental.py --jumlah 10 --benih 7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import universe  # noqa: E402

AKAR = Path(__file__).resolve().parent.parent

# Nama baris di laporan Yahoo, dengan cadangan.
BARIS = {
    "Pendapatan": ("laba_rugi", ["Total Revenue", "Operating Revenue"], "ttm"),
    # "Net Income" = laba yang diatribusikan ke induk, padanan NetIncomeLoss di
    # XBRL. "Net Income Common Stockholders" sudah dikurangi dividen preferen
    # dan sekuritas partisipasi, jadi definisinya berbeda.
    "Laba": ("laba_rugi", ["Net Income", "Net Income Common Stockholders"], "ttm"),
    "OCF": ("arus_kas", ["Operating Cash Flow"], "ttm"),
    "Aset": ("neraca", ["Total Assets"], "akhir"),
    "Ekuitas": ("neraca", ["Stockholders Equity", "Common Stock Equity"], "akhir"),
}


def dari_yahoo(ticker: str) -> tuple[pd.Timestamp | None, dict]:
    import yfinance as yf
    t = yf.Ticker(ticker)
    lap = {"laba_rugi": t.quarterly_income_stmt, "arus_kas": t.quarterly_cashflow,
           "neraca": t.quarterly_balance_sheet}
    hasil, akhir = {}, None
    for metrik, (jenis, nama, cara) in BARIS.items():
        df = lap[jenis]
        if df is None or df.empty:
            continue
        df = df.reindex(sorted(df.columns), axis=1)
        baris = next((n for n in nama if n in df.index), None)
        if baris is None:
            continue
        seri = df.loc[baris].dropna()
        if seri.empty:
            continue
        if cara == "ttm":
            if len(seri) < 4:
                continue
            hasil[metrik] = float(seri.iloc[-4:].sum())
            akhir = seri.index[-1] if akhir is None else akhir
        else:
            hasil[metrik] = float(seri.iloc[-1])
    return akhir, hasil


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jumlah", type=int, default=10)
    p.add_argument("--benih", type=int, default=7)
    p.add_argument("--ticker", nargs="+")
    a = p.parse_args(argv)

    f = pd.read_csv(AKAR / "data" / "fundamental.csv", index_col="Ticker")
    f = f.join(universe.muat()[["Sektor"]])
    calon = f[(f["Sektor"] != "Financials") & f["Laba"].notna() & (f["Basis"] == "TTM-4Q")]
    sampel = a.ticker or list(calon.sample(a.jumlah * 2, random_state=a.benih).index)

    baris, dicek = [], 0
    for t in sampel:
        if dicek >= (len(a.ticker) if a.ticker else a.jumlah):
            break
        try:
            akhir, y = dari_yahoo(t)
        except Exception as e:
            print(f"{t}: Yahoo gagal ({type(e).__name__})", file=sys.stderr)
            continue
        periode = pd.Timestamp(f.loc[t, "Periode_Lapkeu"])
        if akhir is None or abs((akhir - periode).days) > 10:
            print(f"{t}: periode beda (kita {periode.date()}, Yahoo {akhir.date() if akhir is not None else '-'}), dilewati",
                  file=sys.stderr)
            continue
        dicek += 1
        for m, nilai_y in y.items():
            kita = f.loc[t, m]
            selisih = (kita - nilai_y) / abs(nilai_y) * 100 if nilai_y else float("nan")
            baris.append({"Ticker": t, "Metrik": m, "SEC_juta": kita / 1e6, "Yahoo_juta": nilai_y / 1e6,
                          "Selisih_%": selisih})

    hasil = pd.DataFrame(baris)
    if hasil.empty:
        print("Tidak ada emiten yang periodenya cocok.")
        return 1
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(hasil.round(2).to_string(index=False))
    abs_selisih = hasil["Selisih_%"].abs()
    print(f"\n{dicek} emiten, {len(hasil)} angka dibandingkan. "
          f"Selisih ≤ 2%: {(abs_selisih <= 2).sum()} ({(abs_selisih <= 2).mean():.0%}). "
          f"Median selisih absolut: {abs_selisih.median():.2f}%.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
