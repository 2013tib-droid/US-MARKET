"""Menyusun hasil/semua.csv: universe + indikator + faktor + red flag.

Urutan dan nama kolom di sini adalah kontrak dengan dashboard dan dengan
`screener.py --dari-csv`. Menambah kolom boleh; mengubah arti kolom yang
sudah ada wajib menaikkan usmarket.VERSI_SKEMA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import faktor, teknikal
from .harga import Panel

BENCHMARK = "SPY"

# Likuiditas minimum (docs/01-metodologi.md §4). Syarat market cap ≥ $1
# miliar menyusul di Fase 2, saat jumlah saham beredar tersedia dari SEC.
MIN_HARGA = 5.0
MIN_NILAI_JUTA = 10.0

KOLOM = [
    # Identitas
    "Nama", "Sektor", "Industri", "Indeks", "Harga", "Tanggal_Data", "Bar",
    # Likuiditas
    "Nilai20H_JutaUSD", "VolSpike", "LolosLikuiditas",
    # Momentum
    "Ret12_1", "Ret6_1", "Mom_RiskAdj", "Z_Momentum", "RS_Rating",
    # Low-Vol
    "Vol1T", "Beta", "MaxDD1T", "Z_LowVol",
    # Teknikal
    "MA50", "MA150", "MA200", "MA200_Naik", "High52", "Low52", "ATR14", "RSI14",
    "RS_vs_SPX", "RS_HighBaru", "TrendTemplate",
    # Keputusan
    "Flag",
]

PEMBULATAN = {
    "Harga": 2, "Nilai20H_JutaUSD": 1, "VolSpike": 2,
    "Ret12_1": 1, "Ret6_1": 1, "Mom_RiskAdj": 2, "Z_Momentum": 2,
    "Vol1T": 1, "Beta": 2, "MaxDD1T": 1, "Z_LowVol": 2,
    "MA50": 2, "MA150": 2, "MA200": 2, "High52": 2, "Low52": 2,
    "ATR14": 2, "RSI14": 1, "RS_vs_SPX": 1,
}


def _flag(r: pd.Series, tanggal_panel: str) -> str:
    # `== True`, bukan `if r.get(...)`: untuk ticker yang berhasil kolom ini
    # NaN, dan bool(NaN) di Python bernilai True.
    if r.get("_Gagal") == True:  # noqa: E712
        return "GAGAL-UNDUH"
    flag = []
    if not r.get("LolosLikuiditas"):
        flag.append("TIPIS")
    if pd.isna(r.get("Z_Momentum")) or pd.isna(r.get("Z_LowVol")):
        flag.append("DATA-KURANG")
    if r.get("Tanggal_Data") and r["Tanggal_Data"] < tanggal_panel:
        flag.append("BASI")
    if r.get("_SektorKecil"):
        flag.append("SEKTOR-KECIL")
    return ";".join(flag)


def bangun(universe: pd.DataFrame, panel: Panel) -> pd.DataFrame:
    """Satu baris per ticker universe, termasuk yang gagal diunduh.

    Ticker yang gagal tetap muncul dengan flag GAGAL-UNDUH: tabel yang diam-
    diam kehilangan 30 emiten lebih berbahaya daripada tabel yang jujur
    menyebut 30 emiten tidak ada datanya.
    """
    spy = panel.satu(BENCHMARK) if BENCHMARK in panel.tickers else None
    spy_tutup = spy["tutup"] if spy is not None else None
    spy_adj = spy["tutup_adj"] if spy is not None else None

    baris = {}
    for ticker in universe.index:
        if ticker not in panel.tickers:
            baris[ticker] = {"_Gagal": True}
            continue
        df = panel.satu(ticker)
        if df.empty:
            baris[ticker] = {"_Gagal": True}
            continue
        r = teknikal.hitung(df, spy_tutup)
        r.update(faktor.mentah_momentum(df["tutup_adj"]))
        r.update(faktor.mentah_lowvol(df["tutup_adj"], spy_adj))
        baris[ticker] = r

    tabel = universe.join(pd.DataFrame.from_dict(baris, orient="index"), how="left")
    tabel.index.name = "Ticker"
    for kolom in ("Ret12_1", "Ret6_1", "Vol1T", "Beta", "MaxDD1T", "_RS_Mentah"):
        if kolom not in tabel:
            tabel[kolom] = np.nan
    tabel = faktor.hitung_faktor(tabel)

    tabel["LolosLikuiditas"] = ((tabel["Harga"] >= MIN_HARGA)
                                & (tabel["Nilai20H_JutaUSD"] >= MIN_NILAI_JUTA))
    tanggal_panel = panel.tutup.index[-1].date().isoformat()
    tabel["Flag"] = tabel.apply(_flag, axis=1, tanggal_panel=tanggal_panel)

    for kolom in KOLOM:
        if kolom not in tabel:
            tabel[kolom] = np.nan
    tabel = tabel[KOLOM]
    for kolom, desimal in PEMBULATAN.items():
        tabel[kolom] = pd.to_numeric(tabel[kolom], errors="coerce").round(desimal)
    return tabel
