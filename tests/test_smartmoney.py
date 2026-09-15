from datetime import date

import numpy as np
import pandas as pd
import pytest

from usmarket import faktor, smartmoney


def form4(transaksi: str, pemilik="COOK TIMOTHY D", cik="0001214156", jabatan="CEO",
          catatan="", tambahan="") -> str:
    """Kerangka dokumen Form 4 seperti yang dikirim EDGAR."""
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <schemaVersion>X0508</schemaVersion>
  <documentType>4</documentType>
  <periodOfReport>2026-09-01</periodOfReport>
  {tambahan}
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>{cik}</rptOwnerCik><rptOwnerName>{pemilik}</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer>
      <officerTitle>{jabatan}</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>{transaksi}</nonDerivativeTable>
  {catatan}
</ownershipDocument>"""


def trx(kode="P", lembar="1000", harga="150.00", arah="A", footnote="") -> str:
    harga_el = f"<transactionPricePerShare><value>{harga}</value></transactionPricePerShare>" if harga \
        else '<transactionPricePerShare><footnoteId id="F1"/></transactionPricePerShare>'
    return f"""<nonDerivativeTransaction>
    <securityTitle><value>Common Stock</value></securityTitle>
    <transactionDate><value>2026-09-01</value></transactionDate>
    <transactionCoding><transactionFormType>4</transactionFormType>
      <transactionCode>{kode}</transactionCode><equitySwapInvolved>0</equitySwapInvolved></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>{lembar}</value></transactionShares>
      {harga_el}
      <transactionAcquiredDisposedCode><value>{arah}</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
    {footnote}
  </nonDerivativeTransaction>"""


def test_form4_pembelian_pasar_terbuka():
    (t,) = smartmoney.baca_form4(form4(trx()))
    assert t["Ticker"] == "AAPL" and t["CIK"] == 320193
    assert t["Kode"] == "P" and t["Nilai"] == pytest.approx(150_000)
    assert t["Pemilik"] == "COOK TIMOTHY D" and t["Pemilik_CIK"] == 1214156
    assert t["Jabatan"] == "CEO" and t["Peran"] == "pejabat"
    assert t["Rencana10b5"] is False


def test_form4_eksekusi_opsi_dan_hibah_tetap_terbaca_tapi_bukan_beli():
    # Dibaca supaya bisa dibedakan dari "tidak ada transaksi"; yang menyaring
    # kode P/S adalah ringkas_insider, bukan parsernya.
    hasil = smartmoney.baca_form4(form4(trx("M", harga="0") + trx("A", harga="")))
    assert [t["Kode"] for t in hasil] == ["M", "A"]
    assert hasil[1]["Harga"] is None and hasil[1]["Nilai"] is None


def test_form4_rencana_10b5_dari_kotak_centang_dan_dari_catatan_kaki():
    kotak = smartmoney.baca_form4(form4(trx("S", arah="D"), tambahan="<aff10b5One>1</aff10b5One>"))
    assert kotak[0]["Rencana10b5"] is True

    kaki = smartmoney.baca_form4(form4(
        trx("S", arah="D", footnote='<footnoteId id="F1"/>'),
        catatan='<footnotes><footnote id="F1">Sale pursuant to a Rule 10b5-1 trading plan '
                'adopted on May 2, 2026.</footnote></footnotes>'))
    assert kaki[0]["Rencana10b5"] is True

    # Catatan kaki yang tidak menyebut rencana tidak boleh menggugurkan transaksi.
    biasa = smartmoney.baca_form4(form4(
        trx("S", arah="D", footnote='<footnoteId id="F1"/>'),
        catatan='<footnotes><footnote id="F1">Harga rata-rata tertimbang.</footnote></footnotes>'))
    assert biasa[0]["Rencana10b5"] is False


def test_form4_rusak_tidak_melempar():
    assert smartmoney.baca_form4(b"<html>403 Forbidden</html>") == []


def transaksi(baris) -> pd.DataFrame:
    kolom = ["Ticker", "Tanggal", "Kode", "Nilai", "Pemilik", "Pemilik_CIK", "Rencana10b5"]
    return pd.DataFrame(baris, columns=kolom)


HARI_INI = date(2026, 9, 15)


def test_ringkas_net_beli_dikurangi_jual():
    t = transaksi([
        ["AAPL", "2026-09-01", "P", 1_000_000, "A", 1, False],
        ["AAPL", "2026-08-01", "S", 3_000_000, "B", 2, False],
        # Di luar jendela 90 hari.
        ["AAPL", "2026-01-01", "P", 9_000_000, "C", 3, False],
        # Terjadwal: tidak masuk hitungan, tapi dihitung jumlahnya.
        ["AAPL", "2026-09-02", "S", 5_000_000, "D", 4, True],
        # Bukan pasar terbuka.
        ["AAPL", "2026-09-03", "M", 8_000_000, "E", 5, False],
    ])
    r = smartmoney.ringkas_insider(t, HARI_INI).loc["AAPL"]
    assert r["Insider_Beli90H_JutaUSD"] == pytest.approx(1.0)
    assert r["Insider_Jual90H_JutaUSD"] == pytest.approx(3.0)
    assert r["Insider_Net90H_JutaUSD"] == pytest.approx(-2.0)
    assert r["Insider_Pembeli90H"] == 1 and r["Insider_Penjual90H"] == 1
    assert r["Insider_Rencana90H"] == 1
    assert r["Insider_Transaksi90H"] == 2


def test_cluster_buy_butuh_dua_orang_dalam_jendela_30_hari():
    dua_orang = transaksi([["X", "2026-09-01", "P", 1e6, "A", 1, False],
                           ["X", "2026-09-20", "P", 1e6, "B", 2, False]])
    r = smartmoney.ringkas_insider(dua_orang, date(2026, 9, 25)).loc["X"]
    assert bool(r["Insider_ClusterBuy"]) and r["Insider_ClusterTgl"] == "2026-09-20"

    satu_orang = transaksi([["X", "2026-09-01", "P", 1e6, "A", 1, False],
                            ["X", "2026-09-20", "P", 1e6, "A", 1, False]])
    assert not smartmoney.ringkas_insider(satu_orang, date(2026, 9, 25)).loc["X"]["Insider_ClusterBuy"]

    berjauhan = transaksi([["X", "2026-07-01", "P", 1e6, "A", 1, False],
                           ["X", "2026-09-01", "P", 1e6, "B", 2, False]])
    assert not smartmoney.ringkas_insider(berjauhan, date(2026, 9, 25)).loc["X"]["Insider_ClusterBuy"]


def test_ringkas_tanpa_transaksi_menghasilkan_tabel_kosong_berkolom():
    r = smartmoney.ringkas_insider(transaksi([]), HARI_INI)
    assert len(r) == 0 and "Insider_Net90H_JutaUSD" in r.columns


def test_buang_kedaluwarsa():
    t = transaksi([["X", "2026-09-01", "P", 1e6, "A", 1, False],
                   ["X", "2025-09-01", "P", 1e6, "A", 1, False]])
    sisa = smartmoney.buang_kedaluwarsa(t, HARI_INI)
    assert list(sisa["Tanggal"]) == ["2026-09-01"]


def tabel_uji(n=10, **kolom) -> pd.DataFrame:
    dasar = pd.DataFrame({
        "Sektor": ["Tech"] * n,
        "Harga": [100.0] * n,
        "MCap_MiliarUSD": [10.0] * n,
        "Insider_Net90H_JutaUSD": [0.0] * n,
        "Institusi_Delta": [0.0] * n,
        "Insider_ClusterBuy": [False] * n,
        "_SM_Ada": [True] * n,
    }, index=[f"T{i}" for i in range(n)])
    for k, v in kolom.items():
        dasar[k] = v
    return dasar


def test_z_smartmoney_naik_dengan_beli_orang_dalam_relatif_market_cap():
    t = tabel_uji()
    t.loc["T0", "Insider_Net90H_JutaUSD"] = 50.0     # 0,5% market cap
    t.loc["T1", "Insider_Net90H_JutaUSD"] = -50.0
    h = smartmoney.hitung(t)
    assert h.loc["T0", "Insider_Net_PctMCap"] == pytest.approx(0.5)
    assert h.loc["T0", "Z_SmartMoney"] > 0 > h.loc["T1", "Z_SmartMoney"]


def test_cluster_buy_menambah_satu_poin_penuh():
    t = tabel_uji()
    t.loc["T0", "Insider_ClusterBuy"] = True
    h = smartmoney.hitung(t)
    assert h.loc["T0", "Z_SmartMoney"] == pytest.approx(smartmoney.BONUS_CLUSTER)
    assert h.loc["T1", "Z_SmartMoney"] == pytest.approx(0.0)


def test_komponen_kosong_netral_tapi_baris_tanpa_data_tetap_nan():
    t = tabel_uji()
    t.loc["T0", "Institusi_Delta"] = np.nan          # kosong = netral
    t.loc["T1", "_SM_Ada"] = False                   # tidak ada di smartmoney.csv
    h = smartmoney.hitung(t)
    assert h.loc["T0", "Z_SmartMoney"] == pytest.approx(0.0)
    assert np.isnan(h.loc["T1", "Z_SmartMoney"])


def test_flag_short_tinggi_dan_insider_jual():
    assert smartmoney.flag_smartmoney(pd.Series({"Short_PctFloat": 25.0})) == ["SHORT-TINGGI"]
    assert smartmoney.flag_smartmoney(pd.Series({"Short_PctFloat": 5.0})) == []
    assert smartmoney.flag_smartmoney(pd.Series({"Insider_Net90H_JutaUSD": -12.0})) == ["INSIDER-JUAL"]
    # Jual kecil bukan sinyal; begitu juga kolom kosong.
    assert smartmoney.flag_smartmoney(pd.Series({"Insider_Net90H_JutaUSD": -1.0})) == []
    assert smartmoney.flag_smartmoney(pd.Series(dtype=object)) == []


def test_revisi_target_memakai_snapshot_sekitar_tiga_bulan():
    riwayat = pd.DataFrame({
        "Tanggal": ["2026-06-16", "2026-09-08"],   # 91 hari lalu, dan minggu lalu
        "Ticker": ["AAPL", "AAPL"],
        "Target_Rata": [100.0, 118.0],
    })
    sekarang = pd.Series({"AAPL": 120.0})
    revisi, umur = smartmoney.revisi_target(riwayat, sekarang, HARI_INI)
    assert revisi["AAPL"] == pytest.approx(20.0)     # dibanding 100, bukan 118
    assert umur["AAPL"] == 91


def test_revisi_target_kosong_selama_riwayat_belum_tiga_bulan():
    riwayat = pd.DataFrame({"Tanggal": ["2026-09-08"], "Ticker": ["AAPL"], "Target_Rata": [118.0]})
    revisi, _ = smartmoney.revisi_target(riwayat, pd.Series({"AAPL": 120.0}), HARI_INI)
    assert np.isnan(revisi["AAPL"])


def test_hari_bursa_ke_earnings():
    # 15 Sep 2026 Selasa; 21 Sep Senin = 4 hari bursa.
    hasil = smartmoney.hari_bursa_ke(pd.Series(["2026-09-21", "2026-09-14", None]), HARI_INI)
    assert hasil.iloc[0] == 4
    assert hasil.iloc[1] == -1
    assert np.isnan(hasil.iloc[2])


def test_delta_snapshot_tanpa_pembanding_nan():
    baru = pd.Series({"A": 70.0, "B": 50.0})
    lama = pd.Series({"A": 68.0})
    d = smartmoney.delta_snapshot(baru, lama)
    assert d["A"] == pytest.approx(2.0) and np.isnan(d["B"])


# --- faktor Growth --------------------------------------------------------

def test_z_growth_butuh_dua_komponen():
    n = 8
    t = pd.DataFrame({
        "Sektor": ["Tech"] * n,
        "Harga": [100.0] * n,
        "Rev_YoY": np.linspace(0.0, 0.35, n),
        "Laba_YoY": np.linspace(0.0, 0.7, n),
    }, index=[f"T{i}" for i in range(n)])
    t.loc["T0", ["Rev_YoY", "Laba_YoY"]] = [np.nan, 0.1]   # hanya satu komponen
    h = faktor.hitung_growth(t)
    assert np.isnan(h.loc["T0", "Z_Growth"])
    assert h.loc["T7", "Z_Growth"] > h.loc["T1", "Z_Growth"]


def test_target_upside_dan_pe_forward():
    t = pd.DataFrame({"Sektor": ["Tech"] * 2, "Harga": [100.0, 50.0],
                      "Target_Rata": [120.0, 45.0], "EPS_Fwd": [5.0, -1.0]},
                     index=["A", "B"])
    h = faktor.hitung_growth(t)
    assert h.loc["A", "Target_Upside"] == pytest.approx(20.0)
    assert h.loc["B", "Target_Upside"] == pytest.approx(-10.0)
    assert h.loc["A", "PE_Fwd"] == pytest.approx(20.0)
    assert np.isnan(h.loc["B", "PE_Fwd"])            # EPS forward negatif: tanpa kelipatan
