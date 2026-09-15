"""Menyusun hasil/semua.csv: universe + indikator + faktor + red flag.

Urutan dan nama kolom di sini adalah kontrak dengan dashboard dan dengan
`screener.py --dari-csv`. Menambah kolom boleh; mengubah arti kolom yang
sudah ada wajib menaikkan usmarket.VERSI_SKEMA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import faktor, smartmoney, teknikal, valuasi
from .harga import Panel

BENCHMARK = "SPY"

# Likuiditas minimum (docs/01-metodologi.md §4).
MIN_HARGA = 5.0
MIN_NILAI_JUTA = 10.0
MIN_MCAP_MILIAR = 1.0

KOLOM = [
    # Identitas
    "Nama", "Sektor", "Industri", "Indeks", "Harga", "MCap_MiliarUSD", "Tanggal_Data", "Bar",
    "Basis", "Periode_Lapkeu", "Earnings_Berikut", "Hari_Ke_Earnings",
    # Likuiditas
    "Nilai20H_JutaUSD", "VolSpike", "LolosLikuiditas",
    # Value
    "EV_EBITDA", "PE_TTM", "PB", "PE_Fwd", "EBITDA_EV", "E_P", "FCF_Yield", "Z_Value",
    # Quality
    "ROIC", "ROE", "GrossMargin", "GM_Stabilitas5T", "NetDebt_EBITDA", "Akrual",
    "ROA_Variabilitas5T", "OCF_Laba", "F_Score", "Z_Altman", "Cakupan_Bunga", "Z_Quality",
    # Momentum
    "Ret12_1", "Ret6_1", "Mom_RiskAdj", "Z_Momentum", "RS_Rating",
    # Low-Vol
    "Vol1T", "Beta", "MaxDD1T", "Z_LowVol",
    # Growth & revisi
    "Rev_CAGR3", "EPS_CAGR3", "Target_Rata", "Target_Upside", "Target_Revisi", "Rekom_Rata",
    "Jumlah_Analis", "Surprise_Terakhir", "Z_Growth",
    # Smart money
    "Insider_Net90H_JutaUSD", "Insider_Beli90H_JutaUSD", "Insider_Jual90H_JutaUSD",
    "Insider_Pembeli90H", "Insider_ClusterBuy", "Insider_Net_PctMCap", "Insider_Terakhir",
    "Institusi_Pct", "Institusi_Delta", "Short_PctFloat", "Short_Ratio", "Z_SmartMoney",
    # Yield & pertumbuhan
    "DivYield", "Buyback_Yield", "Shareholder_Yield", "Rev_YoY", "Laba_YoY", "Dilusi_YoY",
    # Teknikal
    "MA50", "MA150", "MA200", "MA200_Naik", "High52", "Low52", "ATR14", "RSI14",
    "RS_vs_SPX", "RS_HighBaru", "TrendTemplate",
    # Keputusan
    "Flag", "Keyakinan",
]

# Rasio yang disimpan dalam persen supaya terbaca tanpa kalkulator. Kolom
# dari data/smartmoney.csv tidak ada di sini: berkas itu sudah menyimpan
# persen sebagai persen (lihat scripts/perbarui_smartmoney.py).
PERSEN = ["EBITDA_EV", "E_P", "FCF_Yield", "ROIC", "ROE", "GrossMargin", "Akrual",
          "DivYield", "Buyback_Yield", "Shareholder_Yield", "Rev_YoY", "Laba_YoY",
          "Rev_CAGR3", "EPS_CAGR3"]

PEMBULATAN = {
    "Harga": 2, "MCap_MiliarUSD": 2, "Nilai20H_JutaUSD": 1, "VolSpike": 2,
    "EV_EBITDA": 1, "PE_TTM": 1, "PB": 2, "PE_Fwd": 1, "EBITDA_EV": 1, "E_P": 1,
    "FCF_Yield": 1, "Z_Value": 2,
    "ROIC": 1, "ROE": 1, "GrossMargin": 1, "GM_Stabilitas5T": 1, "NetDebt_EBITDA": 2, "Akrual": 1,
    "ROA_Variabilitas5T": 1, "OCF_Laba": 2, "Z_Altman": 2, "Cakupan_Bunga": 1, "Z_Quality": 2,
    "Ret12_1": 1, "Ret6_1": 1, "Mom_RiskAdj": 2, "Z_Momentum": 2,
    "Vol1T": 1, "Beta": 2, "MaxDD1T": 1, "Z_LowVol": 2,
    "Rev_CAGR3": 1, "EPS_CAGR3": 1, "Target_Rata": 2, "Target_Upside": 1, "Target_Revisi": 1,
    "Rekom_Rata": 2, "Surprise_Terakhir": 1, "Z_Growth": 2,
    "Insider_Net90H_JutaUSD": 2, "Insider_Beli90H_JutaUSD": 2, "Insider_Jual90H_JutaUSD": 2,
    "Insider_Net_PctMCap": 3, "Institusi_Pct": 1, "Institusi_Delta": 2, "Short_PctFloat": 2,
    "Short_Ratio": 1, "Z_SmartMoney": 2, "Hari_Ke_Earnings": 0,
    "DivYield": 2, "Buyback_Yield": 2, "Shareholder_Yield": 2, "Rev_YoY": 1, "Laba_YoY": 1,
    "Dilusi_YoY": 1, "MA50": 2, "MA150": 2, "MA200": 2, "High52": 2, "Low52": 2,
    "ATR14": 2, "RSI14": 1, "RS_vs_SPX": 1, "Keyakinan": 0,
}


# Jangan masuk sebelum lapkeu: gap 10–20% dua arah biasa terjadi di AS
# (docs/01-metodologi.md §3, Pilar 5).
HARI_EARNINGS_DEKAT = 5


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
    hari = r.get("Hari_Ke_Earnings")
    if pd.notna(hari) and 0 <= hari <= HARI_EARNINGS_DEKAT:
        flag.append("EARNINGS-DEKAT")
    if ada_fundamental:
        flag += valuasi.flag_fundamental(r)
    if r.get("_SM_Ada") == True:  # noqa: E712
        flag += smartmoney.flag_smartmoney(r)
    return flag


def bangun(universe: pd.DataFrame, panel: Panel, fundamental: pd.DataFrame | None = None,
           smart: pd.DataFrame | None = None) -> pd.DataFrame:
    """Satu baris per ticker universe, termasuk yang gagal diunduh.

    Ticker yang gagal tetap muncul dengan flag GAGAL-UNDUH: tabel yang diam-
    diam kehilangan 30 emiten lebih berbahaya daripada tabel yang jujur
    menyebut 30 emiten tidak ada datanya.

    `fundamental` = isi data/fundamental.csv, `smart` = data/smartmoney.csv.
    Keduanya boleh kosong: tabel tetap jadi, hanya tanpa kolom yang berasal
    dari sana (perilaku Fase 1 dan Fase 2).
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

    ada_smart = smart is not None and len(smart) > 0
    if ada_smart:
        tambahan = smart.drop(columns=[k for k in smart.columns if k in tabel.columns])
        tabel = tabel.join(tambahan, how="left")
        tabel["_SM_Ada"] = tabel.index.isin(smart.index)
        tabel = smartmoney.hitung(tabel)
        tabel["Hari_Ke_Earnings"] = smartmoney.hari_bursa_ke(
            tabel["Earnings_Berikut"], panel.tutup.index[-1].date())
    tabel = faktor.hitung_growth(tabel)

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
