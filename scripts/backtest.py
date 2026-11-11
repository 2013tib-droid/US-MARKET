#!/usr/bin/env python3
"""Backtest terbatas skor komposit: 2015–sekarang, rebalance bulanan,
10 saham skor tertinggi, dibandingkan SPY.

Syarat "selesai" kedua Fase 4 di docs/04-roadmap.md — dan syarat yang paling
mudah disalahgunakan, jadi batasannya ditulis di muka:

**Survivorship bias.** Konstituen yang dipakai adalah konstituen *hari ini*.
Emiten yang bangkrut, diakuisisi, atau dikeluarkan dari indeks antara 2015
dan sekarang tidak ada di universe, jadi backtest ini melihat masa lalu
dengan daftar pemenang. Hasilnya **pasti** lebih baik dari kenyataan, dan
selisihnya tidak bisa diukur tanpa universe historis berbayar. Angka di sini
adalah batas atas, bukan perkiraan.

**Look-ahead pada fundamental.** Skor butuh Quality, Value, dan Growth, yang
di repo ini hanya ada sebagai snapshot terakhir — bukan deret waktu. Karena
itu backtest ini **hanya memakai faktor dari harga** (Momentum dan Low-Vol),
yang bisa dihitung ulang dengan benar untuk tiap tanggal rebalance. Bobotnya
dinormalisasi ke dua faktor itu saja. Jadi yang diuji adalah bagian skor
yang bisa diuji jujur, bukan seluruh skor — dan itu harus disebut ketika
hasilnya dilaporkan.

**Rezim dihitung ulang** tiap tanggal rebalance dari ^GSPC dan ^VIX sampai
tanggal itu saja, jadi bobotnya bergerak seperti yang akan terjadi sungguhan.

Butuh jaringan: harga harian seluruh universe sejak 2014.

    python scripts/backtest.py --mulai 2015-01-01
    python scripts/backtest.py --mulai 2015-01-01 --n 10 --keluaran hasil/backtest.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import faktor, makro, universe  # noqa: E402

AKAR = Path(__file__).resolve().parent.parent
PEMBANDING = "SPY"
# Faktor yang bisa dihitung ulang untuk tiap tanggal masa lalu dari harga saja.
FAKTOR_HARGA = ("Momentum", "LowVol")
HARI_SETAHUN = 252


def skor_pada(tanggal, tutup: pd.DataFrame, sektor: pd.Series,
              bobot: dict[str, float]) -> pd.Series:
    """Skor komposit dari faktor harga, memakai data sampai `tanggal` saja."""
    sampai = tutup.loc[:tanggal]
    if len(sampai) < HARI_SETAHUN + 21:
        return pd.Series(dtype=float)
    spy = sampai[PEMBANDING] if PEMBANDING in sampai else None

    baris = {}
    for t in sampai.columns:
        if t == PEMBANDING:
            continue
        deret = sampai[t].dropna()
        if len(deret) < HARI_SETAHUN + 21:
            continue
        r = faktor.mentah_momentum(deret)
        r.update(faktor.mentah_lowvol(deret, spy))
        baris[t] = r
    if not baris:
        return pd.Series(dtype=float)

    t = pd.DataFrame.from_dict(baris, orient="index")
    t["Sektor"] = sektor.reindex(t.index).fillna("Tidak diketahui")
    for kolom in ("Ret12_1", "Ret6_1", "Vol1T", "Beta", "MaxDD1T", "_RS_Mentah"):
        if kolom not in t:
            t[kolom] = np.nan
    t = faktor.hitung_faktor(t)
    # Bobot dinormalisasi ke dua faktor harga: bagian skor yang bisa diuji
    # tanpa look-ahead fundamental.
    b = {f: bobot[f] for f in FAKTOR_HARGA}
    if sum(b.values()) == 0:
        # Rezim risk-on memberi Low-Vol nol; momentum sendirian tetap sah.
        b = {"Momentum": 1.0, "LowVol": 0.0}
    return makro.skor_faktor(t, b)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mulai", default="2015-01-01")
    p.add_argument("--n", type=int, default=10, help="Jumlah saham yang dipegang")
    p.add_argument("--keluaran", type=Path, help="Simpan return bulanan ke CSV")
    p.add_argument("--biaya-bps", type=float, default=10.0,
                   help="Biaya sekali jalan per pergantian posisi, basis poin")
    a = p.parse_args(argv)

    uni = universe.muat()
    tickers = list(uni.index) + [PEMBANDING, makro_spx := "^GSPC", makro_vix := "^VIX"]
    awal_unduh = (pd.Timestamp(a.mulai) - pd.Timedelta(days=500)).date().isoformat()
    print(f"Mengunduh {len(tickers)} ticker sejak {awal_unduh}…", file=sys.stderr)
    try:
        import yfinance as yf
        mentah = yf.download(tickers, start=awal_unduh, auto_adjust=True,
                             progress=False, group_by="column")
        # Tabel kosong, bukan galat, adalah cara yfinance melaporkan jaringan
        # yang diblokir. Tanpa pemeriksaan ini skrip mati jauh di bawah
        # dengan galat yang menyesatkan.
        if mentah is None or mentah.empty:
            raise RuntimeError("Yahoo mengembalikan tabel kosong")
        tutup = mentah["Close"].dropna(how="all")
        if tutup.empty:
            raise RuntimeError("tidak ada harga penutupan yang terbaca")
    except Exception as e:
        print(f"Unduhan gagal ({type(e).__name__}: {e}). Backtest butuh jaringan ke Yahoo.",
              file=sys.stderr)
        return 2

    spx = tutup[makro_spx].dropna() if makro_spx in tutup else None
    vix = tutup[makro_vix].dropna() if makro_vix in tutup else None
    harga = tutup.drop(columns=[c for c in (makro_spx, makro_vix) if c in tutup])

    tanggal = harga.loc[a.mulai:].resample("ME").last().index
    sektor = uni["Sektor"] if "Sektor" in uni else pd.Series(dtype=object)

    baris, dipegang = [], []
    for i in range(len(tanggal) - 1):
        t0, t1 = tanggal[i], tanggal[i + 1]
        rezim = makro.tentukan(spx.loc[:t0], vix.loc[:t0] if vix is not None else None) \
            if spx is not None and len(spx.loc[:t0]) >= makro.MA_PANJANG else None
        bobot = rezim.bobot if rezim else makro.BOBOT_REZIM[makro.NETRAL]

        skor = skor_pada(t0, harga, sektor, bobot)
        if skor.empty:
            continue
        pilih = list(skor.nlargest(a.n).index)

        # Return bulan berikutnya: masuk di harga t0, keluar di t1. Ini masih
        # optimistis — harga masuk sungguhan adalah open sesi berikutnya
        # (lihat syarat Fase 5) — tapi tidak look-ahead.
        p0 = harga.loc[t0, pilih]
        p1 = harga.loc[t1, pilih]
        ret = float((p1 / p0 - 1).mean())
        ganti = len(set(pilih) - set(dipegang))
        ret -= (ganti / a.n) * (a.biaya_bps / 1e4) * 2  # beli + jual
        dipegang = pilih

        spy_ret = float(harga.loc[t1, PEMBANDING] / harga.loc[t0, PEMBANDING] - 1) \
            if PEMBANDING in harga else np.nan
        baris.append({"Tanggal": t1.date().isoformat(), "Rezim": rezim.nama if rezim else "—",
                      "Return": ret, "SPY": spy_ret, "Ganti": ganti,
                      "Pilihan": ";".join(pilih)})

    if not baris:
        print("Tidak ada periode yang bisa dihitung.", file=sys.stderr)
        return 1
    h = pd.DataFrame(baris)
    if a.keluaran:
        a.keluaran.parent.mkdir(parents=True, exist_ok=True)
        h.to_csv(a.keluaran, index=False, encoding="utf-8")
        print(f"{len(h)} bulan → {a.keluaran}")

    def ringkas(r: pd.Series) -> dict:
        r = r.dropna()
        tahunan = (1 + r).prod() ** (12 / len(r)) - 1
        vol = r.std() * np.sqrt(12)
        kumulatif = (1 + r).cumprod()
        dd = float((kumulatif / kumulatif.cummax() - 1).min())
        return {"CAGR_%": round(tahunan * 100, 2), "Vol_%": round(vol * 100, 2),
                "Return_per_Risiko": round(tahunan / vol, 3) if vol else np.nan,
                "MaxDD_%": round(dd * 100, 2)}

    sistem, spy = ringkas(h["Return"]), ringkas(h["SPY"])
    print(f"\n{len(h)} bulan, {h['Tanggal'].iloc[0]} – {h['Tanggal'].iloc[-1]}, "
          f"{a.n} saham, biaya {a.biaya_bps:.0f} bps sekali jalan")
    print(pd.DataFrame({"Sistem (faktor harga saja)": sistem, PEMBANDING: spy}).to_string())

    lolos = (sistem["Return_per_Risiko"] or 0) >= (spy["Return_per_Risiko"] or 0)
    print(f"\nReturn per risiko: sistem {sistem['Return_per_Risiko']} vs "
          f"{PEMBANDING} {spy['Return_per_Risiko']} → {'LOLOS' if lolos else 'GAGAL'}")
    print("\nBACA DENGAN DUA CATATAN INI:\n"
          "1. Survivorship bias: konstituen yang dipakai adalah konstituen hari ini, jadi\n"
          "   angka di atas adalah batas atas, bukan perkiraan.\n"
          "2. Hanya faktor harga (Momentum, Low-Vol) yang diuji; Quality, Value, dan Growth\n"
          "   tidak punya deret waktu di repo ini, jadi bagian skor itu belum teruji.\n"
          "Kalau GAGAL: bobot TIDAK diutak-atik sampai lolos. Fase berhenti dan alasannya\n"
          "ditulis di docs/04-roadmap.md — itu aturan fase ini.")
    return 0 if lolos else 1


if __name__ == "__main__":
    sys.exit(main())
