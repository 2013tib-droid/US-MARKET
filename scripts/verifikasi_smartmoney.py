#!/usr/bin/env python3
"""Cocokkan data/smartmoney.csv dengan sumber independen, untuk syarat
"selesai" Fase 3 di docs/04-roadmap.md.

Tiga pemeriksaan, dua otomatis dan satu manual:

1. **Insider net 90 hari** dibandingkan dengan ringkasan transaksi orang
   dalam versi Yahoo (`Ticker.insider_transactions`). Yahoo membaca Form 4
   yang sama tapi mengelompokkannya sendiri, jadi selisih kecil wajar;
   yang dicari adalah selisih besar atau tanda yang berlawanan.
2. **Rincian transaksi** dari data/insider.csv dicetak apa adanya supaya
   bisa dicocokkan baris per baris dengan OpenInsider dan dengan Form 4
   aslinya di EDGAR — tautannya ikut dicetak.
3. **Short interest** tidak punya pembanding gratis yang bisa diunduh, jadi
   yang dicetak adalah angka kita beserta tanggal dan tautan ke halaman
   FINRA/Nasdaq untuk dibaca manusia.

    python scripts/verifikasi_smartmoney.py --jumlah 10
    python scripts/verifikasi_smartmoney.py --ticker AAPL NVDA JPM
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import smartmoney, universe  # noqa: E402

AKAR = Path(__file__).resolve().parent.parent
SMARTMONEY = AKAR / "data" / "smartmoney.csv"
INSIDER = AKAR / "data" / "insider.csv"

URL_OPENINSIDER = "http://openinsider.com/screener?s={t}"
URL_EDGAR = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={t}&type=4&dateb=&owner=include&count=40"
URL_SHORT = "https://www.nasdaq.com/market-activity/stocks/{t}/short-interest"


def net_dari_yahoo(ticker: str, hari: int = smartmoney.JENDELA_HARI) -> float | None:
    """Beli − jual pasar terbuka (juta USD) dari tabel orang dalam Yahoo.

    Yahoo menyebut jenis transaksinya dalam teks bebas ("Purchase at price
    …", "Sale at price …", "Stock Award(Grant)"), bukan kode Form 4, jadi
    penyaringnya kata, bukan kode. Rencana 10b5-1 tidak ditandai sama sekali
    di sini — itu salah satu alasan sumber utamanya EDGAR, bukan Yahoo.
    """
    import yfinance as yf

    df = yf.Ticker(ticker).insider_transactions
    if df is None or df.empty:
        return None
    df = df.copy()
    kolom = {k.lower(): k for k in df.columns}
    k_tgl = kolom.get("start date") or kolom.get("date")
    k_nilai = kolom.get("value")
    k_jenis = kolom.get("transaction") or kolom.get("text")
    if not (k_tgl and k_nilai and k_jenis):
        return None
    tgl = pd.to_datetime(df[k_tgl], errors="coerce")
    batas = pd.Timestamp.today().normalize() - pd.Timedelta(days=hari)
    df = df[tgl.notna() & (tgl >= batas)]
    jenis = df[k_jenis].astype(str).str.lower()
    nilai = pd.to_numeric(df[k_nilai], errors="coerce").fillna(0)
    beli = nilai[jenis.str.contains("purchase")].sum()
    jual = nilai[jenis.str.contains("sale")].sum()
    return float(beli - jual) / 1e6


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jumlah", type=int, default=10, help="Emiten yang diperiksa (yang paling ramai dulu)")
    p.add_argument("--ticker", nargs="+")
    p.add_argument("--tanpa-yahoo", action="store_true", help="Cetak angka kita saja, tanpa membandingkan")
    a = p.parse_args(argv)

    if not SMARTMONEY.exists():
        print(f"{SMARTMONEY} belum ada. Jalankan scripts/perbarui_smartmoney.py dulu.", file=sys.stderr)
        return 1
    sm = pd.read_csv(SMARTMONEY, index_col="Ticker")
    insider = pd.read_csv(INSIDER, dtype={"Akses": str}) if INSIDER.exists() else pd.DataFrame()

    if a.ticker:
        sampel = [universe.normalisasi_ticker(t) for t in a.ticker]
    else:
        # Emiten yang paling banyak transaksinya: di situ selisih paling
        # mungkin muncul, dan di situ pula angkanya paling berarti.
        ramai = pd.to_numeric(sm["Insider_Transaksi90H"], errors="coerce").fillna(0)
        sampel = list(ramai.sort_values(ascending=False).head(a.jumlah).index)

    baris = []
    for t in sampel:
        if t not in sm.index:
            print(f"{t}: tidak ada di smartmoney.csv", file=sys.stderr)
            continue
        r = sm.loc[t]
        kita = pd.to_numeric(r.get("Insider_Net90H_JutaUSD"), errors="coerce")
        yahoo = None
        if not a.tanpa_yahoo:
            try:
                yahoo = net_dari_yahoo(t)
            except Exception as e:
                print(f"{t}: Yahoo gagal ({type(e).__name__})", file=sys.stderr)
        baris.append({
            "Ticker": t,
            "Net_kita_jt": kita,
            "Net_yahoo_jt": yahoo,
            "Beda_jt": (kita - yahoo) if yahoo is not None and pd.notna(kita) else None,
            "Transaksi": r.get("Insider_Transaksi90H"),
            "Rencana10b5": r.get("Insider_Rencana90H"),
            "Cluster": r.get("Insider_ClusterBuy"),
            "Short_%float": r.get("Short_PctFloat"),
            "Institusi_%": r.get("Institusi_Pct"),
        })

    hasil = pd.DataFrame(baris)
    if hasil.empty:
        print("Tidak ada emiten yang bisa diperiksa.")
        return 1
    with pd.option_context("display.width", 220, "display.max_rows", 200):
        print(hasil.round(2).to_string(index=False))
    print("\nYahoo tidak menandai rencana 10b5-1 dan mengelompokkan transaksi dengan caranya "
          "sendiri, jadi selisih kecil wajar. Yang harus dicurigai: tanda berlawanan, atau "
          "selisih yang sebesar angkanya sendiri.")

    print("\n--- Rincian untuk dicocokkan manual (OpenInsider & Form 4 asli) ---")
    for t in hasil["Ticker"]:
        print(f"\n{t}  OpenInsider: {URL_OPENINSIDER.format(t=t)}")
        print(f"{' ' * len(t)}  EDGAR Form 4: {URL_EDGAR.format(t=t)}")
        print(f"{' ' * len(t)}  Short interest (FINRA via Nasdaq): {URL_SHORT.format(t=t.lower())}")
        if len(insider):
            detail = insider[insider["Ticker"] == t]
            detail = detail[detail["Kode"].isin([smartmoney.KODE_BELI, smartmoney.KODE_JUAL])]
            if len(detail):
                kolom = ["Tanggal", "Kode", "Lembar", "Harga", "Nilai", "Pemilik", "Jabatan",
                         "Rencana10b5", "Akses"]
                print(detail.sort_values("Tanggal")[kolom].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
