"""Uji perakitan hasil/semua.csv: kolom kontrak dengan dashboard, gabungan
tiga sumber data (harga, SEC, smart money), dan red flag yang lahir dari
gabungan itu."""

import numpy as np
import pandas as pd

from usmarket import harga, tabel


def panel(tickers, hari=320, mulai="2025-06-02") -> harga.Panel:
    idx = pd.bdate_range(mulai, periods=hari)
    naik = pd.DataFrame({t: 50 * 1.002 ** np.arange(hari) for t in tickers}, index=idx)
    volume = pd.DataFrame(2_000_000.0, index=idx, columns=tickers)
    return harga.Panel(buka=naik, tinggi=naik * 1.01, rendah=naik * 0.99, tutup=naik,
                       tutup_adj=naik, volume=volume, gagal=[])


def universe(tickers) -> pd.DataFrame:
    return pd.DataFrame({"Nama": tickers, "Sektor": "Information Technology",
                         "Industri": "Software", "Indeks": "SP500"},
                        index=pd.Index(tickers, name="Ticker"))


TICKERS = [f"T{i}" for i in range(8)]


def smartmoney_csv(**ubah) -> pd.DataFrame:
    df = pd.DataFrame({
        "Insider_Net90H_JutaUSD": 0.0, "Insider_Beli90H_JutaUSD": 0.0,
        "Insider_Jual90H_JutaUSD": 0.0, "Insider_Pembeli90H": 0, "Insider_ClusterBuy": False,
        "Institusi_Pct": 70.0, "Institusi_Delta": 0.0, "Short_PctFloat": 3.0, "Short_Ratio": 2.0,
        "Target_Rata": 120.0, "Rekom_Rata": 2.0, "Jumlah_Analis": 20, "EPS_Fwd": 5.0,
        "Target_Revisi": 1.0, "Surprise_Terakhir": 2.0, "Earnings_Berikut": None,
    }, index=pd.Index(TICKERS, name="Ticker"))
    for k, v in ubah.items():
        df[k] = v
    return df


def test_kolom_kontrak_lengkap_dan_berurutan():
    hasil = tabel.bangun(universe(TICKERS), panel(TICKERS + ["SPY"]), None, smartmoney_csv())
    assert list(hasil.columns) == tabel.KOLOM
    assert hasil["Z_SmartMoney"].notna().all()
    # Tanpa data fundamental, faktor Growth tetap bisa dihitung dari revisi
    # target dan surprise — dua komponen, batas minimumnya.
    assert hasil["Z_Growth"].notna().all()


def test_tanpa_smartmoney_kolomnya_ada_tapi_kosong():
    hasil = tabel.bangun(universe(TICKERS), panel(TICKERS + ["SPY"]))
    assert list(hasil.columns) == tabel.KOLOM
    assert hasil["Z_SmartMoney"].isna().all()
    assert hasil["Insider_Net90H_JutaUSD"].isna().all()


def test_flag_smartmoney_dan_earnings_masuk_kolom_flag():
    smart = smartmoney_csv()
    smart.loc["T0", "Short_PctFloat"] = 35.0
    smart.loc["T1", "Insider_Net90H_JutaUSD"] = -25.0
    tiga_hari_lagi = pd.bdate_range("2025-06-02", periods=323)[-1].date().isoformat()
    smart.loc["T2", "Earnings_Berikut"] = tiga_hari_lagi
    hasil = tabel.bangun(universe(TICKERS), panel(TICKERS + ["SPY"]), None, smart)
    assert "SHORT-TINGGI" in hasil.loc["T0", "Flag"]
    assert "INSIDER-JUAL" in hasil.loc["T1", "Flag"]
    assert "EARNINGS-DEKAT" in hasil.loc["T2", "Flag"]
    assert "SHORT-TINGGI" not in hasil.loc["T3", "Flag"]


def test_emiten_di_luar_smartmoney_csv_tidak_diberi_skor_nol():
    smart = smartmoney_csv().drop(index=["T5"])
    hasil = tabel.bangun(universe(TICKERS), panel(TICKERS + ["SPY"]), None, smart)
    assert np.isnan(hasil.loc["T5", "Z_SmartMoney"])
    assert hasil.loc["T0", "Z_SmartMoney"] == 0.0
