"""Rezim pasar: overlay yang mengubah bobot faktor, bukan pemilih saham.

Alasannya ada di [01 §3 Pilar 4](../docs/01-metodologi.md): faktor yang
bagus tahun ini bisa juru kunci tahun depan, jadi bobotnya harus bergerak
mengikuti keadaan pasar — tapi tidak boleh mematikan faktor sama sekali,
karena "mematikan" adalah taruhan waktu yang menyamar sebagai kehati-hatian.

Dua hal yang sengaja dipisahkan di modul ini:

**Penentu bobot** hanya SPX terhadap MA50/MA200 dan VIX. Keduanya harian,
gratis, dan tidak direvisi ke belakang.

**Konteks** — yield curve, spread kredit high-yield, dan breadth — dihitung
dan ditampilkan, tapi *tidak* mengubah bobot. Dua yang pertama dari FRED,
yang butuh jaringan dan kunci API, jadi rezim tetap bisa ditentukan tanpa
keduanya; kalau ia ikut menentukan bobot, satu sumber mati berarti seluruh
skor berubah arti diam-diam. Breadth dihitung sendiri dari universe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# --- ambang (docs/01-metodologi.md §3, Pilar 4) ----------------------------

VIX_STRES = 25.0
VIX_PANIK = 35.0
BREADTH_OVERSOLD = 30.0
BREADTH_EUFORIA = 80.0
KURVA_TERBALIK = 0.0
SPREAD_HY_KETAT = 5.0

# Momentum-crash guard: pelajaran 2009 dan 2020. Setelah pasar jatuh dalam,
# pantulan pertamanya dipimpin saham yang paling hancur — persis yang
# skor momentumnya paling buruk. Momentum yang tidak dipotong akan membeli
# pemenang lama tepat ketika kepemimpinan pasar berganti.
GUARD_JATUH = 0.20        # SPX pernah turun ≥ 20% dalam 12 bulan terakhir
GUARD_PANTUL = 0.15       # dan sudah naik ≥ 15% dari dasarnya
GUARD_HARI_PANTUL = 63    # dalam ≤ 3 bulan bursa
GUARD_HARI_AKTIF = 126    # bobot momentum dipotong selama 6 bulan bursa

HARI_SETAHUN = 252
MA_PENDEK = 50
MA_PANJANG = 200

RISK_ON = "Risk-on"
NETRAL = "Netral"
RISK_OFF = "Risk-off"
GUARD = "Momentum-crash guard"

# Bobot per rezim, dalam poin (jumlahnya 100). Ini **titik awal**, bukan
# hasil optimasi: bobot yang dioptimasi ke masa lalu biasanya cuma overfit.
# Uji sensitivitasnya ada di scripts/uji_sensitivitas.py.
BOBOT_REZIM = {
    RISK_ON: {"Quality": 25, "Momentum": 30, "Value": 15, "Growth": 20, "SmartMoney": 10, "LowVol": 0},
    NETRAL:  {"Quality": 30, "Momentum": 25, "Value": 20, "Growth": 15, "SmartMoney": 10, "LowVol": 0},
    RISK_OFF: {"Quality": 35, "Momentum": 10, "Value": 20, "Growth": 10, "SmartMoney": 10, "LowVol": 15},
    GUARD:   {"Quality": 30, "Momentum": 10, "Value": 30, "Growth": 10, "SmartMoney": 15, "LowVol": 5},
}

# Nama faktor → kolom z-score di hasil/semua.csv.
KOLOM_FAKTOR = {"Quality": "Z_Quality", "Momentum": "Z_Momentum", "Value": "Z_Value",
                "Growth": "Z_Growth", "SmartMoney": "Z_SmartMoney", "LowVol": "Z_LowVol"}


@dataclass
class Rezim:
    """Rezim satu tanggal, beserta angka yang menghasilkannya.

    Alasannya ikut disimpan supaya banner dashboard bisa menjelaskan diri
    sendiri: "Risk-off" tanpa sebab hanya memindahkan tebakan ke pembaca.
    """

    nama: str
    guard_aktif: bool = False
    alasan: list[str] = field(default_factory=list)
    konteks: list[str] = field(default_factory=list)
    spx: float | None = None
    spx_ma50: float | None = None
    spx_ma200: float | None = None
    vix: float | None = None
    breadth: float | None = None
    kurva: float | None = None
    spread_hy: float | None = None

    @property
    def bobot(self) -> dict[str, float]:
        return dict(BOBOT_REZIM[self.nama])

    def ringkas(self) -> str:
        teks = self.nama
        if self.alasan:
            teks += " — " + "; ".join(self.alasan)
        return teks

    def ke_dict(self) -> dict:
        return {"rezim": self.nama, "guard_aktif": self.guard_aktif,
                "alasan": self.alasan, "konteks": self.konteks,
                "spx": self.spx, "spx_ma50": self.spx_ma50, "spx_ma200": self.spx_ma200,
                "vix": self.vix, "breadth_pct_di_atas_ma200": self.breadth,
                "kurva_10y2y": self.kurva, "spread_hy": self.spread_hy,
                "bobot": self.bobot}


def _akhir(s: pd.Series | None) -> float | None:
    if s is None or len(s) == 0:
        return None
    nilai = pd.to_numeric(s, errors="coerce").dropna()
    return float(nilai.iloc[-1]) if len(nilai) else None


def guard_momentum(spx: pd.Series, hari_setahun: int = HARI_SETAHUN) -> tuple[bool, str | None]:
    """Momentum-crash guard: pasar pernah jatuh dalam, lalu memantul cepat.

    Dua syarat harus terpenuhi bersama, dan urutannya penting — dasar yang
    dipakai adalah titik terendah *setelah* puncaknya, bukan titik terendah
    mana pun dalam setahun. Guard bertahan `GUARD_HARI_AKTIF` hari bursa
    sejak pantulannya memenuhi syarat, jadi ia tidak berkedip mati-hidup
    mengikuti harga harian.

    Mengembalikan (aktif, tanggal_pemicu).
    """
    harga = pd.to_numeric(spx, errors="coerce").dropna()
    if len(harga) < 60:
        return False, None

    # Guard dievaluasi pada tiap hari dalam jendela aktifnya, lalu diambil
    # pemicu terakhir: kalau syaratnya terpenuhi tiga bulan lalu, guard masih
    # menyala hari ini walau harga hari ini sudah jauh di atas dasarnya.
    jendela = harga.iloc[-(GUARD_HARI_AKTIF + 1):]
    pemicu = None
    for i in range(len(jendela)):
        posisi = len(harga) - len(jendela) + i
        lalu = harga.iloc[max(0, posisi - hari_setahun):posisi + 1]
        if len(lalu) < 60:
            continue
        puncak = lalu.cummax()
        turun = lalu / puncak - 1
        if turun.min() > -GUARD_JATUH:
            continue
        # Dasar = titik terendah setelah drawdown terdalam tercapai.
        dasar_idx = lalu.idxmin()
        setelah = lalu.loc[dasar_idx:]
        if len(setelah) < 2 or len(setelah) > GUARD_HARI_PANTUL + 1:
            continue
        dasar = float(setelah.iloc[0])
        if dasar > 0 and float(setelah.iloc[-1]) / dasar - 1 >= GUARD_PANTUL:
            pemicu = lalu.index[-1]
    if pemicu is None:
        return False, None
    tanggal = pemicu.date().isoformat() if hasattr(pemicu, "date") else str(pemicu)
    return True, tanggal


def breadth_di_atas_ma200(harga_akhir: pd.Series, ma200: pd.Series) -> float | None:
    """Persentase emiten universe yang harganya di atas MA200-nya."""
    h = pd.to_numeric(harga_akhir, errors="coerce")
    m = pd.to_numeric(ma200, errors="coerce")
    ada = h.notna() & m.notna() & (m > 0)
    if ada.sum() == 0:
        return None
    return float((h[ada] > m[ada]).mean() * 100)


def tentukan(spx: pd.Series, vix: pd.Series | None = None, breadth: float | None = None,
             kurva: float | None = None, spread_hy: float | None = None) -> Rezim:
    """Rezim hari ini dari histori SPX harian, plus VIX dan konteks opsional.

    `spx` adalah deret penutupan `^GSPC` (atau proksinya) berurutan naik.
    Semua argumen lain boleh kosong: yang hilang tidak diam-diam dianggap
    nol, ia hanya tidak ikut menjelaskan.
    """
    harga = pd.to_numeric(spx, errors="coerce").dropna()
    akhir = float(harga.iloc[-1]) if len(harga) else None
    ma50 = float(harga.rolling(MA_PENDEK).mean().iloc[-1]) if len(harga) >= MA_PENDEK else None
    ma200 = float(harga.rolling(MA_PANJANG).mean().iloc[-1]) if len(harga) >= MA_PANJANG else None
    vix_kini = _akhir(vix)

    guard_aktif, guard_tanggal = guard_momentum(harga)

    alasan: list[str] = []
    di_bawah_ma200 = akhir is not None and ma200 is not None and akhir < ma200
    di_atas_ma200 = akhir is not None and ma200 is not None and akhir > ma200
    di_atas_ma50 = akhir is not None and ma50 is not None and akhir > ma50
    stres = vix_kini is not None and vix_kini > VIX_STRES

    if di_bawah_ma200:
        alasan.append(f"SPX {akhir:,.0f} di bawah MA200 {ma200:,.0f}")
    if stres:
        alasan.append(f"VIX {vix_kini:.1f} > {VIX_STRES:.0f}"
                      + (" (panik)" if vix_kini > VIX_PANIK else ""))

    if di_bawah_ma200 or stres:
        nama = RISK_OFF
    elif di_atas_ma200 and di_atas_ma50 and vix_kini is not None and vix_kini < VIX_STRES:
        nama = RISK_ON
        alasan.append(f"SPX di atas MA50 dan MA200, VIX {vix_kini:.1f}")
    else:
        nama = NETRAL
        # Netral adalah "tidak cukup bukti untuk salah satunya", jadi
        # sebabnya harus disebut — paling sering VIX yang tidak terbaca.
        if ma200 is None:
            alasan.append("histori SPX < 200 hari, MA200 belum ada")
        elif vix_kini is None:
            alasan.append("VIX tidak terbaca")
        elif di_atas_ma200 and not di_atas_ma50:
            alasan.append(f"SPX di atas MA200 tapi di bawah MA50 {ma50:,.0f}")

    # Guard menang atas ketiganya: ia justru menyala pada pemulihan awal,
    # yang tanpa guard akan terbaca risk-on dan memberi momentum bobot
    # terbesar tepat di saat paling salah.
    if guard_aktif:
        nama = GUARD
        alasan.insert(0, f"pantulan setelah jatuh ≥ 20% (terpicu {guard_tanggal})")

    konteks = []
    if breadth is not None:
        catatan = ""
        if breadth < BREADTH_OVERSOLD:
            catatan = " — oversold"
        elif breadth > BREADTH_EUFORIA:
            catatan = " — euforia"
        konteks.append(f"Breadth {breadth:.0f}% di atas MA200{catatan}")
    if kurva is not None:
        konteks.append(f"Kurva 10Y−2Y {kurva:+.2f}"
                       + (" — terbalik" if kurva < KURVA_TERBALIK else ""))
    if spread_hy is not None:
        konteks.append(f"Spread HY {spread_hy:.2f}%"
                       + (" — kredit mengetat" if spread_hy > SPREAD_HY_KETAT else ""))

    return Rezim(nama=nama, guard_aktif=guard_aktif, alasan=alasan, konteks=konteks,
                 spx=akhir, spx_ma50=ma50, spx_ma200=ma200, vix=vix_kini,
                 breadth=breadth, kurva=kurva, spread_hy=spread_hy)


def rezim_historis(spx: pd.Series, vix: pd.Series | None = None,
                   tanggal: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Rezim untuk tiap tanggal di `tanggal` (default: tiap akhir bulan).

    Dipakai syarat "selesai" pertama Fase 4: menghitung ulang rezim 2008,
    2009, 2020, dan 2022 lalu membandingkannya dengan yang akan disebut
    seorang analis untuk periode itu.
    """
    harga = pd.to_numeric(spx, errors="coerce").dropna()
    if tanggal is None:
        tanggal = harga.resample("ME").last().index
    baris = []
    for t in tanggal:
        sampai = harga.loc[:t]
        if len(sampai) < MA_PANJANG:
            continue
        v = pd.to_numeric(vix, errors="coerce").dropna().loc[:t] if vix is not None else None
        r = tentukan(sampai, v)
        baris.append({"Tanggal": t.date().isoformat(), "Rezim": r.nama,
                      "Guard": r.guard_aktif, "SPX": r.spx, "MA200": r.spx_ma200,
                      "VIX": r.vix, "Alasan": "; ".join(r.alasan)})
    return pd.DataFrame(baris)


def skor_faktor(tabel: pd.DataFrame, bobot: dict[str, float]) -> pd.Series:
    """Σ (bobot_rezim[f] × z_sektor[f]), dinormalisasi ke bobot yang terisi.

    Faktor yang kosong untuk satu emiten tidak dianggap nol — itu akan
    menghukum emiten berdata tipis seolah semua faktornya biasa-biasa saja.
    Bobotnya dinormalisasi ke faktor yang ada, persis seperti
    `faktor.gabung_z_berbobot` memperlakukan komponen fundamental.
    """
    kolom = {f: KOLOM_FAKTOR[f] for f in bobot if bobot[f] > 0}
    if not kolom:
        return pd.Series(np.nan, index=tabel.index)
    z = pd.concat({f: pd.to_numeric(tabel.get(k), errors="coerce") if k in tabel
                   else pd.Series(np.nan, index=tabel.index)
                   for f, k in kolom.items()}, axis=1)
    w = pd.Series({f: bobot[f] for f in kolom})
    ada = z.notna()
    total = ada.mul(w, axis=1).sum(axis=1)
    jumlah = z.fillna(0).mul(w, axis=1).sum(axis=1)
    return (jumlah / total.replace(0, np.nan)) * w.sum()


def skor_persentil(mentah: pd.Series) -> pd.Series:
    """Skor akhir 0–100: peringkat persentil Skor_Faktor di universe.

    Persentil, bukan nilai mentahnya, karena ambang 70 di label status harus
    berarti hal yang sama tiap malam. Skor mentah bergeser seluruhnya ketika
    pasar bergerak; peringkat tidak.
    """
    nilai = pd.to_numeric(mentah, errors="coerce")
    return (nilai.rank(pct=True) * 100).round(1).where(nilai.notna())
