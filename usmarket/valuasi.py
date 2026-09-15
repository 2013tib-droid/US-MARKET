"""Metrik yang butuh harga terbaru: market cap, EV, yield valuasi, Altman Z,
serta faktor Value dan Quality (docs/01-metodologi.md §3, Pilar 1–2).

Angka laporan keuangan datang dari data/fundamental.csv (diperbarui mingguan
dari SEC); harga dari run malam. Menggabungkannya di sini, bukan di skrip
mingguan, membuat valuasi selalu memakai harga penutupan terakhir.

Valuasi disimpan sebagai *yield* (EBITDA/EV, laba/harga, FCF/harga), bukan
kelipatan (EV/EBITDA, P/E). Kelipatan patah di penyebut nol dan terbalik
urutannya saat laba negatif; yield tetap berurutan benar. Kelipatan tetap
ditampilkan untuk dibaca manusia.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .faktor import gabung_z_berbobot, z_sektor

KEUANGAN = "Financials"
# Altman Z dirancang untuk perusahaan manufaktur. Untuk utilitas dan REIT —
# aset besar, pendapatan per aset kecil, utang tinggi yang memang wajar —
# rumusnya menyala merah untuk hampir semua emiten, jadi tidak dipakai.
TANPA_ALTMAN = {KEUANGAN, "Real Estate", "Utilities"}

BOBOT_VALUE = {"EBITDA_EV": 0.3, "E_P": 0.3, "FCF_Yield": 0.3, "B_P": 0.1}
BOBOT_VALUE_KEU = {"E_P": 0.5, "B_P": 0.5}
BOBOT_QUALITY = {"ROIC": 0.3, "GrossMargin": 0.2, "GM_Stabil": 0.15, "Leverage_Rendah": 0.15, "Akrual_Rendah": 0.2}
BOBOT_QUALITY_KEU = {"ROE": 0.4, "ROA": 0.3, "ROA_Stabil": 0.3}

FLAG_BERAT = {"DISTRES", "RESTATEMENT", "F-RENDAH", "TIPIS", "GAGAL-UNDUH", "SAHAM-JANGGAL"}

# Altman Z < 1,8 saja menandai 174 emiten pada data 14 Sep 2026, termasuk
# telekomunikasi (VZ, T, TMUS), pipa migas (WMB, KMI, OKE), dan ORCL —
# perusahaan padat modal berperingkat investasi yang rumus manufaktur 1968
# itu salah baca karena aset lancarnya kecil dan pendapatan per asetnya
# rendah. Jadi Z rendah hanya peringatan (ZONA-BAHAYA); flag berat DISTRES
# butuh konfirmasi bahwa laba operasi juga tidak cukup menutup bunga.
# EBIT/bunga < 1,5 kira-kira wilayah peringkat kredit B/CCC.
MIN_CAKUPAN_BUNGA = 1.5

KOLOM_INTI = ["Pendapatan", "Laba", "OCF", "Aset", "Ekuitas", "Saham"]
KOLOM_INTI_KEU = ["Laba", "Aset", "Ekuitas", "Saham"]


def _angka(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def hitung(tabel: pd.DataFrame) -> pd.DataFrame:
    """Tambahkan kolom valuasi, kualitas, dan Z_Value/Z_Quality ke tabel
    yang sudah berisi Harga, Sektor, dan kolom mentah fundamental."""
    t = tabel.copy()
    for k in ("Harga", "Saham", "Utang", "KasPlus", "EBITDA", "EBIT", "Laba", "OCF", "Capex",
              "Ekuitas", "Goodwill", "Intangible", "Dividen", "Buyback", "Penerbitan", "Aset",
              "AsetLancar", "LiabLancar", "LabaDitahan", "Liabilitas", "Pendapatan"):
        t[k] = _angka(t[k]) if k in t else np.nan
    keu = t["Sektor"].eq(KEUANGAN)

    mcap = t["Harga"] * t["Saham"]
    t["MCap_MiliarUSD"] = mcap / 1e9
    ev = mcap + t["Utang"] - t["KasPlus"].fillna(0)
    ev = ev.where(ev > 0)

    ekuitas_nyata = (t["Ekuitas"] - t["Goodwill"].fillna(0) - t["Intangible"].fillna(0)).where(keu, t["Ekuitas"])
    t["EBITDA_EV"] = (t["EBITDA"] / ev).where(~keu)
    t["E_P"] = t["Laba"] / mcap
    t["FCF_Yield"] = ((t["OCF"] - t["Capex"]) / mcap).where(~keu)
    t["B_P"] = ekuitas_nyata / mcap
    t["EV_EBITDA"] = (ev / t["EBITDA"]).where((t["EBITDA"] > 0) & ~keu)
    t["PE_TTM"] = (mcap / t["Laba"]).where(t["Laba"] > 0)
    t["PB"] = (mcap / t["Ekuitas"]).where(t["Ekuitas"] > 0)
    t["DivYield"] = t["Dividen"] / mcap
    t["Buyback_Yield"] = (t["Buyback"].fillna(0) - t["Penerbitan"].fillna(0)) / mcap
    t["Shareholder_Yield"] = t["DivYield"] + t["Buyback_Yield"]

    # Jumlah saham yang salah (mis. saham setara kelas A dikalikan harga
    # kelas B) menghasilkan laba 5× market cap atau nilai buku 50× market cap.
    # Valuasi dari angka seperti itu lebih buruk daripada kosong.
    janggal = (t["E_P"] > 1) | (t["B_P"] > 20) | (t["MCap_MiliarUSD"] < 0.01)
    t["_SahamJanggal"] = janggal.fillna(False)
    for k in ("EBITDA_EV", "E_P", "FCF_Yield", "B_P", "EV_EBITDA", "PE_TTM", "PB", "DivYield",
              "Buyback_Yield", "Shareholder_Yield", "MCap_MiliarUSD"):
        t.loc[t["_SahamJanggal"], k] = np.nan

    pakai_altman = ~t["Sektor"].isin(TANPA_ALTMAN)
    aset = t["Aset"].where(t["Aset"] > 0)
    t["Z_Altman"] = (1.2 * (t["AsetLancar"] - t["LiabLancar"]) / aset
                     + 1.4 * t["LabaDitahan"] / aset
                     + 3.3 * t["EBIT"] / aset
                     + 0.6 * mcap / t["Liabilitas"].where(t["Liabilitas"] > 0)
                     + 1.0 * t["Pendapatan"] / aset).where(pakai_altman & ~t["_SahamJanggal"])
    bunga = _angka(t["BebanBunga"]) if "BebanBunga" in t else pd.Series(np.nan, index=t.index)
    # Tanpa beban bunga yang dilaporkan, cakupan tidak terhingga (tidak ada
    # bunga yang harus ditutup) — kecuali EBIT-nya sendiri negatif.
    t["Cakupan_Bunga"] = (t["EBIT"] / bunga.where(bunga > 0)).where(bunga > 0, np.where(t["EBIT"] <= 0, -np.inf, np.inf))

    # --- faktor ---
    sektor = t["Sektor"].fillna("Tidak diketahui")
    z = {}
    for k in ("EBITDA_EV", "E_P", "FCF_Yield", "B_P"):
        z[k], _ = z_sektor(t[k], sektor)
    t["Z_Value"] = gabung_z_berbobot(
        {k: z[k] for k in BOBOT_VALUE}, BOBOT_VALUE, sektor, min_komponen=2, baris=~keu)
    z_value_keu = gabung_z_berbobot(
        {k: z[k] for k in BOBOT_VALUE_KEU}, BOBOT_VALUE_KEU, sektor, min_komponen=2, baris=keu)
    t["Z_Value"] = t["Z_Value"].where(~keu, z_value_keu)

    q = {}
    for k in ("ROIC", "GrossMargin", "ROE", "ROA"):
        q[k], _ = z_sektor(_angka(t.get(k, pd.Series(np.nan, index=t.index))), sektor)
    q["GM_Stabil"], _ = z_sektor(-_angka(t.get("GM_Stabilitas5T", pd.Series(np.nan, index=t.index))), sektor)
    q["Leverage_Rendah"], _ = z_sektor(-_angka(t.get("NetDebt_EBITDA", pd.Series(np.nan, index=t.index))), sektor)
    q["Akrual_Rendah"], _ = z_sektor(-_angka(t.get("Akrual", pd.Series(np.nan, index=t.index))), sektor)
    q["ROA_Stabil"], _ = z_sektor(-_angka(t.get("ROA_Variabilitas5T", pd.Series(np.nan, index=t.index))), sektor)
    zq = gabung_z_berbobot({k: q[k] for k in BOBOT_QUALITY}, BOBOT_QUALITY, sektor, min_komponen=3, baris=~keu)
    zq_keu = gabung_z_berbobot({k: q[k] for k in BOBOT_QUALITY_KEU}, BOBOT_QUALITY_KEU, sektor,
                               min_komponen=2, baris=keu)
    t["Z_Quality"] = zq.where(~keu, zq_keu)
    return t


def flag_fundamental(r: pd.Series) -> list[str]:
    """Red flag dari laporan keuangan (docs/03-rancang-bangun.md §5)."""
    f = []
    catatan = str(r.get("Catatan") or "")
    if "us-gaap" in catatan or "USD" in catatan:
        f.append("FILER-ASING")
    if "hari lalu" in catatan:
        f.append("LAPKEU-LAMA")
    if pd.notna(r.get("Z_Altman")) and r["Z_Altman"] < 1.8:
        f.append("ZONA-BAHAYA")
        if pd.notna(r.get("Cakupan_Bunga")) and r["Cakupan_Bunga"] < MIN_CAKUPAN_BUNGA:
            f.append("DISTRES")
    if str(r.get("GoingConcern") or "").strip() not in ("", "nan"):
        f.append("GOING-CONCERN")
    if str(r.get("Restatement") or "").strip() not in ("", "nan"):
        f.append("RESTATEMENT")
    if pd.notna(r.get("F_Score")) and r["F_Score"] <= 3:
        f.append("F-RENDAH")
    ocf_laba, ocf_laba_lalu = r.get("OCF_Laba"), r.get("OCF_Laba_Lalu")
    if pd.notna(ocf_laba) and pd.notna(ocf_laba_lalu) and ocf_laba < 0.6 and ocf_laba_lalu < 0.6:
        f.append("LABA-KERTAS")
    if pd.notna(r.get("Dilusi_YoY")) and r["Dilusi_YoY"] > 5:
        f.append("DILUSI")
    gw, ek = _angka(pd.Series([r.get("Goodwill"), r.get("Ekuitas")]))
    if pd.notna(gw) and gw > 0 and pd.notna(ek) and (ek <= 0 or gw / ek > 1):
        f.append("GOODWILL")
    if r.get("_SahamJanggal") == True:  # noqa: E712
        f.append("SAHAM-JANGGAL")
    # Bank tidak dinilai dari utangnya (tidak ada EV, tidak ada NetDebt/EBITDA),
    # dan semua bank punya beban bunga material, jadi flag ini tidak berarti.
    if r.get("Sektor") != KEUANGAN and str(r.get("Tag_Utang") or "").startswith("utang tidak terbaca"):
        f.append("UTANG-TAK-TERBACA")
    return f


def inti_kosong(r: pd.Series) -> int:
    kolom = KOLOM_INTI_KEU if r.get("Sektor") == KEUANGAN else KOLOM_INTI
    return sum(1 for k in kolom if pd.isna(pd.to_numeric(r.get(k), errors="coerce")))


def alasan_keyakinan(r: pd.Series, flag: list[str]) -> list[tuple[int, str]]:
    """Daftar (potongan, alasan) yang membentuk angka Keyakinan."""
    if "GAGAL-UNDUH" in flag or pd.isna(pd.to_numeric(r.get("Laba"), errors="coerce")):
        return [(100, "tidak ada laporan keuangan yang bisa dibaca")]
    a = []
    if r.get("Basis") == "FY":
        a.append((25, "basis tahun fiskal, bukan empat kuartal terakhir"))
    n = inti_kosong(r)
    if n:
        a.append((6 * n, f"{n} metrik inti kosong"))
    if "SEKTOR-KECIL" in flag:
        a.append((10, "pembanding sektor kurang dari 5 emiten"))
    if r.get("Sektor") == KEUANGAN:
        # Metrik penilai utama bank (NIM, NPL, CET1) tidak ada di XBRL
        # non-dimensional; yang tersedia hanya ROE, ROA, dan nilai buku.
        a.append((10, "emiten keuangan: NIM, NPL, dan CET1 tidak tersedia"))
    if "DATA-KURANG" in flag:
        a.append((20, "data kurang (histori harga < 1 tahun atau > 3 metrik inti kosong)"))
    if "LAPKEU-LAMA" in flag:
        a.append((15, "laporan terakhir lebih dari 270 hari lalu"))
    tag_utang = str(r.get("Tag_Utang") or "")
    if r.get("Sektor") != KEUANGAN and (tag_utang.startswith("komponen:") or tag_utang.startswith("utang tidak terbaca")):
        a.append((10, f"utang dari tag komponen atau tak terbaca ({tag_utang})"))
    return a


def keyakinan(r: pd.Series, flag: list[str]) -> float:
    """Seberapa jauh angka di baris ini boleh dipercaya — bukan seberapa
    yakin sahamnya naik. Aturannya meniru analisa.py di Screening-Saham."""
    return float(max(0.0, min(100.0, 100 - sum(p for p, _ in alasan_keyakinan(r, flag)))))
