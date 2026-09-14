"""Faktor kuantitatif. Fase 1 berisi dua faktor yang hanya butuh harga:
Momentum dan Low Volatility. Definisinya ada di docs/01-metodologi.md §3.

Setiap faktor dihitung dalam dua langkah:
1. Metrik mentah per saham (fungsi `mentah_*`), dari histori satu ticker.
2. Normalisasi lintas-saham: z-score di dalam sektornya (`z_sektor`),
   dipangkas di ±3, lalu komponen dirata-rata dan distandarkan ulang.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HARI_SETAHUN = 252
HARI_SEBULAN = 21
BATAS_Z = 3.0
MIN_PER_SEKTOR = 5


def mentah_momentum(adj: pd.Series) -> dict:
    """Return 12-1 dan 6-1 bulan (dalam %), dan volatilitas tahunan (%).

    "12-1" berarti return dari 12 bulan lalu sampai 1 bulan lalu. Bulan
    terakhir sengaja dilewati karena di horizon itu harga cenderung berbalik
    (Jegadeesh 1990), bukan melanjutkan tren.
    """
    if len(adj) <= HARI_SETAHUN:
        return {"Ret12_1": np.nan, "Ret6_1": np.nan}
    t_1 = adj.iloc[-1 - HARI_SEBULAN]
    return {
        "Ret12_1": float((t_1 / adj.iloc[-1 - HARI_SETAHUN] - 1) * 100),
        "Ret6_1": float((t_1 / adj.iloc[-1 - 126] - 1) * 100),
    }


MIN_MINGGU_BETA = 52


def beta_mingguan(adj: pd.Series, spy_adj: pd.Series) -> float:
    """Beta dari return mingguan (penutupan Jumat), sepanjang histori yang
    tersedia, maksimal dua tahun.

    Bukan return harian: diuji pada data Sep 2025–Sep 2026, beta harian
    setahun memberi AAPL 0,69 (korelasi 0,35) dan KO −0,26, sementara
    mingguan dua tahun memberi AAPL 1,07 dan KO 0,12. Return harian berisik
    oleh selisih jam penutupan antarsaham dan pergerakan sehari yang saling
    meniadakan; mingguan dua tahun adalah jendela baku penyedia data seperti
    Bloomberg.
    """
    pasangan = pd.concat([adj, spy_adj], axis=1, join="inner").iloc[-2 * HARI_SETAHUN - 1:]
    mingguan = pasangan.resample("W-FRI").last().pct_change().dropna()
    if len(mingguan) < MIN_MINGGU_BETA or mingguan.iloc[:, 1].var() == 0:
        return np.nan
    return float(mingguan.iloc[:, 0].cov(mingguan.iloc[:, 1]) / mingguan.iloc[:, 1].var())


def mentah_lowvol(adj: pd.Series, spy_adj: pd.Series | None) -> dict:
    """Volatilitas tahunan (dari return harian setahun), beta mingguan
    terhadap SPY, dan max drawdown setahun. Semua dalam %, kecuali beta."""
    if len(adj) <= HARI_SETAHUN:
        return {"Vol1T": np.nan, "Beta": np.nan, "MaxDD1T": np.nan}
    setahun = adj.iloc[-HARI_SETAHUN - 1:]
    ret = setahun.pct_change().dropna()
    vol = float(np.log1p(ret).std() * np.sqrt(HARI_SETAHUN) * 100)
    dd = float((setahun / setahun.cummax() - 1).min() * 100)
    beta = beta_mingguan(adj, spy_adj) if spy_adj is not None else np.nan
    return {"Vol1T": vol, "Beta": beta, "MaxDD1T": dd}


def z_sektor(nilai: pd.Series, sektor: pd.Series, min_n: int = MIN_PER_SEKTOR) -> tuple[pd.Series, pd.Series]:
    """Z-score di dalam sektor, dipangkas di ±BATAS_Z.

    Sektor dengan kurang dari `min_n` nilai terisi tidak punya pembanding
    yang berarti; sahamnya diukur terhadap seluruh universe dan ditandai.
    Mengembalikan (z, sektor_kecil).
    """
    nilai = nilai.astype(float)
    terisi = nilai.notna()
    jumlah = terisi.groupby(sektor).transform("sum")
    kecil = (jumlah < min_n) & terisi

    kelompok = nilai.groupby(sektor)
    rata, simpang = kelompok.transform("mean"), kelompok.transform("std")
    z = (nilai - rata) / simpang.replace(0, np.nan)

    if kecil.any():
        s = nilai.std()
        z_global = (nilai - nilai.mean()) / (s if s and s > 0 else np.nan)
        z = z.where(~kecil, z_global)
    z = z.where(~(terisi & z.isna()), 0.0)  # simpangan nol: semua sama, z = 0
    return z.clip(-BATAS_Z, BATAS_Z), kecil


def gabung_z(komponen: list[pd.Series], sektor: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Rata-rata beberapa z-score, lalu distandarkan ulang di dalam sektor.

    Rata-rata beberapa z-score yang berkorelasi rendah punya simpangan di
    bawah 1; tanpa standarisasi ulang, faktor dengan komponen lebih banyak
    otomatis berbobot lebih kecil di skor komposit. Saham yang salah satu
    komponennya kosong mendapat NaN, bukan rata-rata dari sisanya.
    """
    rata = pd.concat(komponen, axis=1).mean(axis=1, skipna=False)
    return z_sektor(rata, sektor)


def hitung_faktor(tabel: pd.DataFrame) -> pd.DataFrame:
    """Tambahkan Mom_RiskAdj, Z_Momentum, Z_LowVol, dan RS_Rating ke tabel
    yang sudah berisi metrik mentah dan kolom Sektor."""
    t = tabel.copy()
    sektor = t["Sektor"].fillna("Tidak diketahui")
    vol = t["Vol1T"].where(t["Vol1T"] > 0)

    mom12 = t["Ret12_1"] / vol
    mom6 = t["Ret6_1"] / vol
    t["Mom_RiskAdj"] = (mom12 + mom6) / 2
    z12, kecil_a = z_sektor(mom12, sektor)
    z6, _ = z_sektor(mom6, sektor)
    t["Z_Momentum"], _ = gabung_z([z12, z6], sektor)

    z_vol, kecil_b = z_sektor(-t["Vol1T"], sektor)
    z_beta, _ = z_sektor(-t["Beta"], sektor)
    z_dd, _ = z_sektor(t["MaxDD1T"], sektor)  # drawdown negatif: mendekati 0 lebih baik
    t["Z_LowVol"], _ = gabung_z([z_vol, z_beta, z_dd], sektor)

    t["_SektorKecil"] = kecil_a | kecil_b
    t["RS_Rating"] = rs_rating(t["_RS_Mentah"]) if "_RS_Mentah" in t else np.nan
    return t


def rs_rating(mentah: pd.Series) -> pd.Series:
    """Peringkat persentil 1–99 dari return tertimbang, seperti RS rating IBD.
    Beda dengan Z_Momentum: ini lintas seluruh universe, bukan per sektor,
    dan tidak dibagi volatilitas."""
    persen = mentah.rank(pct=True)
    return (persen * 98 + 1).round().where(mentah.notna())
