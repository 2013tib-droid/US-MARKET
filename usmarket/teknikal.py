"""Indikator teknikal per saham: MA, 52 minggu, ATR, RSI, likuiditas,
relative strength terhadap S&P 500, dan trend template.

Semua fungsi menerima histori satu ticker (DataFrame dari Panel.satu) dan
tidak menyentuh jaringan, jadi bisa diuji dengan data buatan.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HARI_SETAHUN = 252
HARI_SEBULAN = 21


def rsi_wilder(tutup: pd.Series, periode: int = 14) -> float:
    selisih = tutup.diff()
    naik = selisih.clip(lower=0).ewm(alpha=1 / periode, adjust=False, min_periods=periode).mean()
    turun = (-selisih.clip(upper=0)).ewm(alpha=1 / periode, adjust=False, min_periods=periode).mean()
    n, t = naik.iloc[-1], turun.iloc[-1]
    if pd.isna(n) or pd.isna(t):
        return np.nan
    if t == 0:
        return 100.0 if n > 0 else 50.0
    return float(100 - 100 / (1 + n / t))


def atr_wilder(df: pd.DataFrame, periode: int = 14) -> float:
    tutup_kemarin = df["tutup"].shift(1)
    rentang = pd.concat([df["tinggi"] - df["rendah"],
                         (df["tinggi"] - tutup_kemarin).abs(),
                         (df["rendah"] - tutup_kemarin).abs()], axis=1).max(axis=1)
    atr = rentang.ewm(alpha=1 / periode, adjust=False, min_periods=periode).mean()
    return float(atr.iloc[-1]) if len(atr) else np.nan


def trend_template(harga, ma50, ma150, ma200, ma200_naik, high52, low52) -> bool:
    """Trend template Minervini, versi harga saja.

    Syaratnya: harga > MA50 > MA150 > MA200, MA200 naik minimal sebulan,
    harga ≥ 25% di atas low 52 minggu, dan ≤ 25% di bawah high 52 minggu.
    Syarat RS rating ≥ 70 dari versi aslinya tidak digabung di sini; RS
    rating tersedia sebagai kolom sendiri supaya bisa difilter terpisah.
    """
    nilai = [harga, ma50, ma150, ma200, high52, low52]
    if any(pd.isna(v) for v in nilai) or pd.isna(ma200_naik):
        return False
    return bool(harga > ma50 > ma150 > ma200
                and ma200_naik
                and harga >= 1.25 * low52
                and harga >= 0.75 * high52)


def hitung(df: pd.DataFrame, spy_tutup: pd.Series | None = None) -> dict:
    """Semua indikator teknikal satu saham. Nilai yang datanya tidak cukup
    dikembalikan sebagai NaN, bukan ditebak."""
    tutup = df["tutup"]
    n = len(tutup)
    hasil: dict = {"Bar": n}
    if n == 0:
        return hasil

    harga = float(tutup.iloc[-1])
    hasil["Harga"] = harga
    hasil["Tanggal_Data"] = tutup.index[-1].date().isoformat()

    def ma(p):
        return float(tutup.iloc[-p:].mean()) if n >= p else np.nan

    hasil["MA50"], hasil["MA150"], hasil["MA200"] = ma(50), ma(150), ma(200)
    if n >= 200 + HARI_SEBULAN:
        ma200_lalu = float(tutup.iloc[-200 - HARI_SEBULAN:-HARI_SEBULAN].mean())
        hasil["MA200_Naik"] = bool(hasil["MA200"] > ma200_lalu)
    else:
        hasil["MA200_Naik"] = np.nan

    if n >= HARI_SETAHUN:
        hasil["High52"] = float(df["tinggi"].iloc[-HARI_SETAHUN:].max())
        hasil["Low52"] = float(df["rendah"].iloc[-HARI_SETAHUN:].min())
    else:
        hasil["High52"] = hasil["Low52"] = np.nan

    hasil["ATR14"] = atr_wilder(df)
    hasil["RSI14"] = rsi_wilder(tutup)

    nilai_harian = tutup * df["volume"]
    hasil["Nilai20H_JutaUSD"] = float(nilai_harian.iloc[-20:].mean() / 1e6) if n >= 20 else np.nan
    vol_rata = df["volume"].iloc[-21:-1].mean() if n >= 21 else np.nan
    hasil["VolSpike"] = float(df["volume"].iloc[-1] / vol_rata) if vol_rata and vol_rata > 0 else np.nan

    hasil["TrendTemplate"] = trend_template(harga, hasil["MA50"], hasil["MA150"], hasil["MA200"],
                                            hasil["MA200_Naik"], hasil["High52"], hasil["Low52"])

    # Relative strength line = harga saham ÷ SPY, pada tanggal yang sama.
    if spy_tutup is not None:
        rs = (tutup / spy_tutup.reindex(tutup.index)).dropna()
        if len(rs) >= 64:
            hasil["RS_vs_SPX"] = float((rs.iloc[-1] / rs.iloc[-64] - 1) * 100)
        else:
            hasil["RS_vs_SPX"] = np.nan
        hasil["RS_HighBaru"] = bool(rs.iloc[-1] >= rs.iloc[-HARI_SETAHUN:].max()) if len(rs) >= HARI_SETAHUN else False

    # Return tertimbang ala IBD untuk RS rating. Peringkat persentilnya baru
    # bisa dihitung setelah semua saham selesai, lihat faktor.rs_rating.
    adj = df["tutup_adj"]
    if len(adj) > HARI_SETAHUN:
        r = [adj.iloc[-1] / adj.iloc[-1 - k * 63] - 1 for k in (1, 2, 3, 4)]
        hasil["_RS_Mentah"] = float(0.4 * r[0] + 0.2 * r[1] + 0.2 * r[2] + 0.2 * r[3])
    else:
        hasil["_RS_Mentah"] = np.nan
    return hasil
