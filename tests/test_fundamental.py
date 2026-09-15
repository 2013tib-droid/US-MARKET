from datetime import date

import numpy as np
import pandas as pd
import pytest

from usmarket import fundamental as fu
from usmarket import valuasi


def f(start, end, val, form="10-K", filed="2026-02-01"):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed}


def i(end, val, form="10-K", filed="2026-02-01"):
    return {"end": end, "val": val, "form": form, "filed": filed}


def facts(usd: dict, shares: dict | None = None) -> dict:
    gaap = {tag: {"units": {"USD": daftar}} for tag, daftar in usd.items()}
    for tag, daftar in (shares or {}).items():
        gaap[tag] = {"units": {"shares": daftar}}
    return {"facts": {"us-gaap": gaap}}


def test_q4_diturunkan_dari_tahunan_dikurangi_sembilan_bulan():
    rev = [f("2025-01-01", "2025-03-31", 90, "10-Q"), f("2025-04-01", "2025-06-30", 90, "10-Q"),
           f("2025-01-01", "2025-06-30", 180, "10-Q"), f("2025-07-01", "2025-09-30", 90, "10-Q"),
           f("2025-01-01", "2025-09-30", 270, "10-Q"), f("2025-01-01", "2025-12-31", 400),
           f("2026-01-01", "2026-03-31", 110, "10-Q")]
    s = fu.seri(facts({"Revenues": rev})["facts"], "Pendapatan")
    q = s.kuartal()
    assert q[date(2025, 12, 31)] == 130
    assert s.ttm(date(2026, 3, 31)) == 90 + 90 + 130 + 110


def test_angka_revisi_dari_laporan_terakhir_menang():
    rev = [f("2025-01-01", "2025-12-31", 400, filed="2026-02-01"),
           f("2025-01-01", "2025-12-31", 390, "10-K/A", filed="2026-05-01")]
    s = fu.seri(facts({"Revenues": rev})["facts"], "Pendapatan")
    assert s.tahunan()[date(2025, 12, 31)] == 390


def test_tag_dengan_periode_terbaru_jadi_utama():
    lama = [f("2016-01-01", "2016-12-31", 100)]
    baru = [f("2025-01-01", "2025-12-31", 400)]
    s = fu.seri(facts({"SalesRevenueNet": lama,
                       "RevenueFromContractWithCustomerExcludingAssessedTax": baru})["facts"], "Pendapatan")
    assert s.tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert s.tahunan()[date(2016, 12, 31)] == 100  # histori lama tetap terisi


def test_jumlah_saham_tidak_diturunkan_dari_ytd():
    sh = [f("2025-01-01", "2025-03-31", 100, "10-Q"), f("2025-01-01", "2025-06-30", 101, "10-Q")]
    s = fu.Seri({(date.fromisoformat(x["start"]), date.fromisoformat(x["end"])): x["val"] for x in sh}, "x")
    assert date(2025, 6, 30) in s.kuartal(turunan=True)       # 101 − 100 = 1: salah untuk saham
    assert date(2025, 6, 30) not in s.kuartal(turunan=False)


def _seri_instan(nilai):
    return fu.Seri({(None, date(2026, 6, 30)): nilai}, "x")


def _ss_kosong():
    return {m: fu.Seri({}, None) for m in fu.TAG}


def test_utang_komponen_tidak_dihitung_ganda():
    cadangan = {"NotesPayable": _seri_instan(5657.0), "SecuredDebt": _seri_instan(360.0),
                "UnsecuredDebt": _seri_instan(5296.0)}
    v, sumber = fu.utang_total(_ss_kosong(), date(2026, 6, 30), cadangan)
    assert v == 5657.0 and sumber == "komponen:NotesPayable"


def test_utang_nol_hanya_bila_bunga_kecil():
    v, sumber = fu.utang_total(_ss_kosong(), date(2026, 6, 30), {}, bunga=1e6, aset=1e10)
    assert v == 0.0 and sumber == "tidak ada tag utang"
    v, sumber = fu.utang_total(_ss_kosong(), date(2026, 6, 30), {}, bunga=5e8, aset=1e10)
    assert v is None and sumber.startswith("utang tidak terbaca")


def test_utang_dari_jadwal_jatuh_tempo():
    cadangan = {t: fu.Seri({(None, date(2025, 12, 31)): 1000.0}, t) for t in fu.JATUH_TEMPO}
    v, sumber = fu.utang_total(_ss_kosong(), date(2026, 6, 30), cadangan)
    assert v == 6000.0 and "jadwal jatuh tempo 2025-12-31" in sumber


def test_piotroski_hitungan_tangan():
    """Dua tahun fiskal; setiap komponen dihitung tangan di komentar.

    ROA 2025 = 100/1100 = 0,091 > 0 (+); OCF 150 > 0 (+);
    ROA 2024 = 80/1000 = 0,080 → naik (+); OCF 150 > laba 100 (+);
    utang/aset 300/1200 = 0,25 < 350/1100 = 0,32 (+);
    rasio lancar 500/250 = 2,0 > 400/250 = 1,6 (+);
    saham 100 ≤ 105 (+); margin kotor 40% < 42,2% (−);
    perputaran aset 1000/1100 = 0,909 > 900/1000 = 0,900 (+).  F = 8.
    """
    usd = {
        "NetIncomeLoss": [f("2025-01-01", "2025-12-31", 100), f("2024-01-01", "2024-12-31", 80)],
        "NetCashProvidedByUsedInOperatingActivities": [f("2025-01-01", "2025-12-31", 150),
                                                       f("2024-01-01", "2024-12-31", 120)],
        "Revenues": [f("2025-01-01", "2025-12-31", 1000), f("2024-01-01", "2024-12-31", 900)],
        "GrossProfit": [f("2025-01-01", "2025-12-31", 400), f("2024-01-01", "2024-12-31", 380)],
        "Assets": [i("2025-12-31", 1200), i("2024-12-31", 1100), i("2023-12-31", 1000)],
        "AssetsCurrent": [i("2025-12-31", 500), i("2024-12-31", 400)],
        "LiabilitiesCurrent": [i("2025-12-31", 250), i("2024-12-31", 250)],
        "StockholdersEquity": [i("2025-12-31", 600), i("2024-12-31", 550)],
        "LongTermDebt": [i("2025-12-31", 300), i("2024-12-31", 350)],
    }
    sh = {"WeightedAverageNumberOfDilutedSharesOutstanding": [f("2025-01-01", "2025-12-31", 100),
                                                               f("2024-01-01", "2024-12-31", 105)]}
    r = fu.ekstrak(facts(usd, sh), hari_ini=date(2026, 3, 1))
    assert r["Basis"] == "FY" and r["Periode_Lapkeu"] == "2025-12-31"
    assert r["F_Rincian"] == "ROA+ OCF+ dROA+ AKRUAL+ LEVERAGE+ CR+ SAHAM+ MARGIN- ATO+"
    assert r["F_Score"] == 8


def test_gabung_facts_pendahulu_laporan_baru_menang():
    lama = facts({"NetIncomeLoss": [f("2025-01-01", "2025-12-31", 100, filed="2026-02-01")]})
    baru = facts({"NetIncomeLoss": [f("2025-01-01", "2025-12-31", 101, filed="2026-08-01")]})
    g = fu.gabung_facts(baru, lama)
    s = fu.seri(g["facts"], "Laba")
    assert s.tahunan()[date(2025, 12, 31)] == 101


def test_filer_asing_tanpa_usgaap():
    r = fu.ekstrak({"facts": {"ifrs-full": {}}})
    assert "tanpa us-gaap" in r["Catatan"]


def _baris_valuasi(**kw):
    dasar = {"Sektor": "Industrials", "Harga": 50.0, "Saham": 1e9, "Utang": 1e10, "KasPlus": 1e9,
             "EBITDA": 5e9, "EBIT": 4e9, "Laba": 2.5e9, "OCF": 3e9, "Capex": 1e9, "Ekuitas": 2e10,
             "Goodwill": 0.0, "Intangible": 0.0, "Dividen": 1e9, "Buyback": 5e8, "Penerbitan": 0.0,
             "Aset": 5e10, "AsetLancar": 1e10, "LiabLancar": 8e9, "LabaDitahan": 1e10,
             "Liabilitas": 3e10, "Pendapatan": 4e10, "BebanBunga": 5e8}
    dasar.update(kw)
    return dasar


def test_valuasi_dasar_dan_saham_janggal():
    t = pd.DataFrame([_baris_valuasi(), _baris_valuasi(Saham=1e6)], index=["A", "B"])
    v = valuasi.hitung(t)
    assert v.loc["A", "MCap_MiliarUSD"] == 50
    assert v.loc["A", "PE_TTM"] == pytest.approx(20)
    assert v.loc["A", "EV_EBITDA"] == pytest.approx((50e9 + 1e10 - 1e9) / 5e9)
    assert v.loc["A", "Cakupan_Bunga"] == pytest.approx(8)
    assert v.loc["B", "_SahamJanggal"] and np.isnan(v.loc["B", "PE_TTM"])


def test_zona_bahaya_bukan_distres_bila_bunga_tertutup():
    r = pd.Series({"Z_Altman": 1.2, "Cakupan_Bunga": 4.0, "Sektor": "Communication Services"})
    assert "ZONA-BAHAYA" in valuasi.flag_fundamental(r) and "DISTRES" not in valuasi.flag_fundamental(r)
    r["Cakupan_Bunga"] = 0.8
    assert "DISTRES" in valuasi.flag_fundamental(r)


def test_bank_tidak_kena_flag_utang():
    r = pd.Series({"Sektor": "Financials", "Tag_Utang": "utang tidak terbaca (bunga material)"})
    assert "UTANG-TAK-TERBACA" not in valuasi.flag_fundamental(r)


def test_utang_tahunan_lama_dipakai_sampai_200_hari():
    cadangan = {"LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities":
                fu.Seri({(None, date(2025, 12, 31)): 131.6e9}, "x")}
    v, sumber = fu.utang_total(_ss_kosong(), date(2026, 6, 30), cadangan)
    assert v == 131.6e9 and sumber.startswith("komponen:") and "2025-12-31" in sumber
    v, _ = fu.utang_total(_ss_kosong(), date(2026, 12, 31), cadangan)
    assert v == 0.0  # sudah lebih dari 200 hari: tidak dipakai


def test_bukti_aktivitas_utang_membuat_utang_tak_terbaca():
    fk = {"us-gaap": {"RepaymentsOfLongTermDebt": {"units": {"USD": [
        {"start": "2026-01-01", "end": "2026-03-31", "val": 15.6e9, "form": "10-Q", "filed": "2026-05-01"}]}}}}
    assert fu.ada_bukti_utang(fk, date(2026, 3, 31), 290e9)
    v, sumber = fu.utang_total(_ss_kosong(), date(2026, 3, 31), {}, bukti_lain=True)
    assert v is None and "penerbitan" in sumber
