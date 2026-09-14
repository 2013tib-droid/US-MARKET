"""Menyusun hasil/semua.csv: universe + indikator + faktor + red flag.

Urutan dan nama kolom di sini adalah kontrak dengan dashboard dan dengan
`screener.py --dari-csv`. Menambah kolom boleh; mengubah arti kolom yang
sudah ada wajib menaikkan usmarket.VERSI_SKEMA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import faktor, teknikal, valuasi
from .harga import Panel

BENCHMARK = "SPY"

# Likuiditas minimum (docs/01-metodologi.md §4).
MIN_HARGA = 5.0
MIN_NILAI_JUTA = 10.0
MIN_MCAP_MILIAR = 1.0

KOLOM = [
    # Identitas
    "Nama", "Sektor", "Industri", "Indeks", "Harga", "MCap_MiliarUSD", "Tanggal_Data", "Bar",
    "Basis", "Periode_Lapkeu",
    # Likuiditas
    "Nilai20H_JutaUSD", "VolSpike", "LolosLikuiditas",
    # Value
    "EV_EBITDA", "PE_TTM", "PB", "EBITDA_EV", "E_P", "FCF_Yield", "Z_Value",
    # Quality
    "ROIC", "ROE", "GrossMargin", "GM_Stabilitas5T", "NetDebt_EBITDA", "Akrual",
    "ROA_Variabilitas5T", "OCF_Laba", "F_Score", "Z_Altman", "Cakupan_Bunga", "Z_Quality",
    # Momentum
    "Ret12_1", "Ret6_1", "Mom_RiskAdj", "Z_Momentum", "RS_Rating",
    # Low-Vol
    "Vol1T", "Beta", "MaxDD1T", "Z_LowVol",
    # Yield & pertumbuhan (Z_Growth menyusul di Fase 3)
    "DivYield", "Buyback_Yield", "Shareholder_Yield", "Rev_YoY", "Laba_YoY", "Dilusi_YoY",
    # Teknikal
    "MA50", "MA150", "MA200", "MA200_Naik", "High52", "Low52", "ATR14", "RSI14",
    "RS_vs_SPX", "RS_HighBaru", "TrendTemplate",
    # Keputusan
    "Flag", "Keyakinan",
]

# Rasio yang disimpan dalam persen supaya terbaca tanpa kalkulator.
PERSEN = ["EBITDA_EV", "E_P", "FCF_Yield", "ROIC", "ROE", "GrossMargin", "Akrual",
          "DivYield", "Buyback_Yield", "Shareholder_Yield", "Rev_YoY", "Laba_YoY"]

PEMBULATAN = {
    "Harga": 2, "MCap_MiliarUSD": 2, "Nilai20H_JutaUSD": 1, "VolSpike": 2,
    "EV_EBITDA": 1, "PE_TTM": 1, "PB": 2, "EBITDA_EV": 1, "E_P": 1, "FCF_Yield": 1, "Z_Value": 2,
    "ROIC": 1, "ROE": 1, "GrossMargin": 1, "GM_Stabilitas5T": 1, "NetDebt_EBITDA": 2, "Akrual": 1,
    "ROA_Variabilitas5T": 1, "OCF_Laba": 2, "Z_Altman": 2, "Cakupan_Bunga": 1, "Z_Quality": 2,
    "Ret12_1": 1, "Ret6_1": 1, "Mom_RiskAdj": 2, "Z_Momentum": 2,
    "Vol1T": 1, "Beta": 2, "MaxDD1T": 1, "Z_LowVol": 2,
    "DivYield": 2, "Buyback_Yield": 2, "Shareholder_Yield": 2, "Rev_YoY": 1, "Laba_YoY": 1,
    "Dilusi_YoY": 1, "MA50": 2, "MA150": 2, "MA200": 2, "High52": 2, "Low52": 2,
    "ATR14": 2, "RSI14": 1, "RS_vs_SPX": 1, "Keyakinan": 0,
}


def _flag(r: pd.Series, tanggal_panel: str, ada_fundamental: bool) -> list[str]:
    # `== True`, bukan `if r.get(...)`: untuk ticker yang berhasil kolom ini
    # NaN, dan bool(NaN) di Python bernilai True.
    if r.get("_Gagal") == True:  # noqa: E712
        return ["GAGAL-UNDUH"]
    flag = []
    if not r.get("LolosLikuiditas"):
        flag.append("TIPIS")
    kurang_harga = pd.isna(r.get("Z_Momentum")) or pd.isna(r.get("Z_LowVol"))
    kurang_lapkeu = ada_fundamental and valuasi.inti_kosong(r) > 3
    if kurang_harga or kurang_lapkeu:
        flag.append("DATA-KURANG")
    if r.get("Tanggal_Data") and r["Tanggal_Data"] < tanggal_panel:
        flag.append("BASI")
    if r.get("_SektorKecil"):
        flag.append("SEKTOR-KECIL")
    if ada_fundamental:
        flag += valuasi.flag_fundamental(r)
    return flag


def bangun(universe: pd.DataFrame, panel: Panel, fundamental: pd.DataFrame | None = None) -> pd.DataFrame:
    """Satu baris per ticker universe, termasuk yang gagal diunduh.

    Ticker yang gagal tetap muncul dengan flag GAGAL-UNDUH: tabel yang diam-
    diam kehilangan 30 emiten lebih berbahaya daripada tabel yang jujur
    menyebut 30 emiten tidak ada datanya.

    `fundamental` = isi data/fundamental.csv. Tanpa itu tabel tetap jadi,
    hanya tanpa kolom valuasi dan kualitas (perilaku Fase 1).
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

    ada_fundamental = fundamental is not None and len(fundamental) > 0
    if ada_fundamental:
        tambahan = fundamental.drop(columns=[k for k in fundamental.columns if k in tabel.columns])
        tabel = tabel.join(tambahan, how="left")
        tabel = valuasi.hitung(tabel)

    mcap = tabel["MCap_MiliarUSD"] if "MCap_MiliarUSD" in tabel else pd.Series(np.nan, index=tabel.index)
    tabel["LolosLikuiditas"] = ((tabel["Harga"] >= MIN_HARGA)
                                & (tabel["Nilai20H_JutaUSD"] >= MIN_NILAI_JUTA)
                                # Market cap yang tidak diketahui tidak menggugurkan.
                                & ~(mcap < MIN_MCAP_MILIAR))
    tanggal_panel = panel.tutup.index[-1].date().isoformat()
    flags = tabel.apply(_flag, axis=1, tanggal_panel=tanggal_panel, ada_fundamental=ada_fundamental)
    tabel["Flag"] = flags.map(";".join)
    if ada_fundamental:
        tabel["Keyakinan"] = [valuasi.keyakinan(r, f) for (_, r), f in zip(tabel.iterrows(), flags)]

    for kolom in KOLOM:
        if kolom not in tabel:
            tabel[kolom] = np.nan
    tabel = tabel[KOLOM].copy()
    for kolom in PERSEN:
        tabel[kolom] = pd.to_numeric(tabel[kolom], errors="coerce") * 100
    # EBIT ÷ bunga nol = tak terhingga; dibatasi supaya CSV tidak berisi "inf".
    tabel["Cakupan_Bunga"] = pd.to_numeric(tabel["Cakupan_Bunga"], errors="coerce").clip(-999, 999)
    for kolom, desimal in PEMBULATAN.items():
        tabel[kolom] = pd.to_numeric(tabel[kolom], errors="coerce").round(desimal)
    return tabel
