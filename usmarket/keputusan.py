"""Dari skor ke keputusan: kolom `Skor`, `Status`, dan `Alasan`.

Saringannya bertahap dan **urutannya penting** ([01 §4](../docs/01-metodologi.md)):
universe → likuiditas → red flag → skor → timing → earnings. Urutan itu
bukan selera: menyaring skor lebih dulu akan memberi peringkat tinggi pada
emiten yang sebenarnya gugur di likuiditas, dan angka itu terlanjur terbaca
sebagai rekomendasi sebelum baris berikutnya membuangnya.

`Alasan` ada supaya dashboard tidak perlu menerjemahkan enam kolom untuk
satu kalimat, dan supaya keputusan yang aneh bisa ditelusuri tanpa membuka
kode: kalau status suatu emiten mengejutkan, alasannya menyebut sendiri
syarat mana yang menentukan.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import makro, valuasi

# Ambang label status (docs/01-metodologi.md §5).
SKOR_KANDIDAT = 70.0
SKOR_TAHAN = 50.0
SHORT_EKSTREM = 30.0
HARI_EARNINGS_DEKAT = 5

AKUMULASI = "AKUMULASI"
PANTAU = "PANTAU"
TUNGGU_LAPKEU = "TUNGGU-LAPKEU"
TAHAN = "TAHAN"
KURANGI = "KURANGI"
HINDARI = "HINDARI"


def _num(t: pd.DataFrame, kolom: str) -> pd.Series:
    if kolom not in t:
        return pd.Series(np.nan, index=t.index)
    return pd.to_numeric(t[kolom], errors="coerce")


def _benar(t: pd.DataFrame, kolom: str) -> pd.Series:
    if kolom not in t:
        return pd.Series(False, index=t.index)
    return t[kolom].map(lambda v: str(v).strip().lower() == "true")


def flag_berat(t: pd.DataFrame) -> pd.Series:
    kolom = t["Flag"].fillna("") if "Flag" in t else pd.Series("", index=t.index)
    return kolom.map(lambda s: bool(set(str(s).split(";")) & valuasi.FLAG_BERAT))


def hitung(tabel: pd.DataFrame, rezim: makro.Rezim | None = None) -> pd.DataFrame:
    """Tambahkan `Rezim`, `Skor_Faktor`, `Skor`, `Status`, dan `Alasan`.

    Tanpa `rezim` (mis. run ad-hoc tanpa ^GSPC) bobot netral dipakai, dan
    kolom `Rezim` menyebutnya apa adanya — bukan diam-diam memakai risk-on.
    """
    t = tabel.copy()
    r = rezim or makro.Rezim(nama=makro.NETRAL, alasan=["SPX tidak tersedia; bobot netral"])
    bobot = r.bobot

    t["Rezim"] = r.nama
    t["Skor_Faktor"] = makro.skor_faktor(t, bobot)
    t["Skor"] = makro.skor_persentil(t["Skor_Faktor"])

    berat = flag_berat(t)
    short = _num(t, "Short_PctFloat")
    likuid = _benar(t, "LolosLikuiditas")
    trend = _benar(t, "TrendTemplate")
    hari = _num(t, "Hari_Ke_Earnings")
    earnings_dekat = hari.between(0, HARI_EARNINGS_DEKAT)
    skor = _num(t, "Skor")
    ma200 = _num(t, "MA200")
    harga = _num(t, "Harga")
    di_bawah_ma200 = (harga < ma200) & ma200.notna() & harga.notna()

    status = pd.Series(TAHAN, index=t.index, dtype=object)
    # Urutan penetapan di bawah adalah kebalikan dari urutan prioritas:
    # yang ditulis belakangan menimpa yang lebih awal.
    status[skor < SKOR_TAHAN] = KURANGI
    status[di_bawah_ma200 & (skor < SKOR_KANDIDAT)] = KURANGI
    kandidat = (skor >= SKOR_KANDIDAT) & ~berat
    status[kandidat] = PANTAU
    status[kandidat & trend] = AKUMULASI
    # Skor tidak terhitung sama sekali bukan "tahan" — itu tidak diketahui.
    status[skor.isna()] = HINDARI
    # Lapkeu dekat menunda apa pun skornya, tapi hanya untuk yang belum
    # gugur: menandai emiten ber-red-flag "TUNGGU-LAPKEU" akan menyiratkan
    # ia layak dibeli setelah lapkeu.
    status[earnings_dekat & ~berat & ~(short > SHORT_EKSTREM)] = TUNGGU_LAPKEU
    status[berat | (short > SHORT_EKSTREM) | ~likuid] = HINDARI

    t["Status"] = status
    t["Alasan"] = [_alasan(baris, r) for _, baris in t.iterrows()]
    return t


def _alasan(baris: pd.Series, rezim: makro.Rezim) -> str:
    """Satu kalimat pendek: syarat mana yang menentukan status baris ini."""
    status = baris.get("Status")
    skor = pd.to_numeric(baris.get("Skor"), errors="coerce")
    bagian: list[str] = []

    flag = str(baris.get("Flag") or "")
    berat = sorted(set(flag.split(";")) & valuasi.FLAG_BERAT)
    short = pd.to_numeric(baris.get("Short_PctFloat"), errors="coerce")
    hari = pd.to_numeric(baris.get("Hari_Ke_Earnings"), errors="coerce")

    if status == HINDARI:
        if berat:
            bagian.append("flag berat " + ", ".join(berat))
        elif pd.notna(short) and short > SHORT_EKSTREM:
            bagian.append(f"short {short:.0f}% float")
        elif not str(baris.get("LolosLikuiditas")).strip().lower() == "true":
            bagian.append("likuiditas gagal")
        elif pd.isna(skor):
            bagian.append("skor tidak terhitung")
        return "; ".join(bagian) or "tidak lolos saringan"

    if pd.notna(skor):
        bagian.append(f"Skor {skor:.0f}")
    if status == TUNGGU_LAPKEU and pd.notna(hari):
        bagian.append(f"lapkeu {hari:.0f} hari bursa lagi")
        return "; ".join(bagian)

    if status in (AKUMULASI, PANTAU):
        bagian.append("tren lolos" if status == AKUMULASI else "tren belum konfirmasi")
    elif status == KURANGI:
        harga = pd.to_numeric(baris.get("Harga"), errors="coerce")
        ma200 = pd.to_numeric(baris.get("MA200"), errors="coerce")
        if pd.notna(harga) and pd.notna(ma200) and harga < ma200:
            bagian.append("harga di bawah MA200")

    # Faktor terkuat emiten ini, supaya "Skor 82" punya isi. Dipilih dari
    # faktor yang memang berbobot di rezim sekarang — menyebut Low-Vol
    # sebagai kekuatan di rezim risk-on menyesatkan, bobotnya nol di sana.
    bobot = rezim.bobot
    z = {f: pd.to_numeric(baris.get(k), errors="coerce")
         for f, k in makro.KOLOM_FAKTOR.items() if bobot.get(f, 0) > 0}
    z = {f: v for f, v in z.items() if pd.notna(v)}
    if z:
        kuat = max(z, key=z.get)
        if z[kuat] > 0.5:
            bagian.append(f"{kuat.lower()} kuat ({z[kuat]:+.1f})")
    if str(baris.get("Insider_ClusterBuy")).strip().lower() == "true":
        bagian.append("insider cluster buy")
    return "; ".join(bagian)
