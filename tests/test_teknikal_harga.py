from datetime import datetime, timezone

import numpy as np
import pandas as pd

from usmarket import harga, teknikal


def histori(tutup, mulai="2024-06-03"):
    idx = pd.bdate_range(mulai, periods=len(tutup))
    tutup = pd.Series(tutup, index=idx, dtype=float)
    return pd.DataFrame({"buka": tutup, "tinggi": tutup * 1.01, "rendah": tutup * 0.99,
                         "tutup": tutup, "tutup_adj": tutup, "volume": 1_000_000.0})


def test_trend_template_uptrend_lolos_downtrend_gagal():
    naik = teknikal.hitung(histori(50 * 1.002 ** np.arange(300)))
    assert naik["TrendTemplate"] is True
    turun = teknikal.hitung(histori(100 * 0.998 ** np.arange(300)))
    assert turun["TrendTemplate"] is False


def test_data_pendek_tidak_ditebak():
    r = teknikal.hitung(histori(np.linspace(10, 20, 120)))
    assert np.isnan(r["MA200"]) and np.isnan(r["High52"])
    assert r["TrendTemplate"] is False


def test_rsi_naik_terus_100():
    assert teknikal.rsi_wilder(pd.Series(np.arange(1, 60, dtype=float))) == 100.0


def test_nilai_transaksi_dan_volspike():
    df = histori(np.full(40, 20.0))
    df.iloc[-1, df.columns.get_loc("volume")] = 3_000_000.0
    r = teknikal.hitung(df)
    assert r["VolSpike"] == 3.0
    assert r["Nilai20H_JutaUSD"] == (19 * 20 + 60) / 20


def test_pisah_kolom_membuang_ticker_kosong():
    idx = pd.DatetimeIndex(["2026-09-10", "2026-09-11"])
    kolom = pd.MultiIndex.from_product([["Open", "High", "Low", "Close", "Adj Close", "Volume"],
                                        ["AAPL", "ZZZZ"]])
    mentah = pd.DataFrame(np.nan, index=idx, columns=kolom)
    for k in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
        mentah[(k, "AAPL")] = [1.0, 2.0]
    bagian = harga.pisah_kolom(mentah)
    assert list(bagian["tutup"].columns) == ["AAPL"]


def test_bar_sesi_berjalan_dibuang():
    idx = pd.DatetimeIndex(["2026-09-10", "2026-09-11"])
    bagian = {"tutup": pd.DataFrame({"AAPL": [1.0, 2.0]}, index=idx),
              "volume": pd.DataFrame({"AAPL": [5.0, 1.0]}, index=idx)}
    saat_sesi = datetime(2026, 9, 11, 18, 0, tzinfo=timezone.utc)
    assert harga.buang_bar_belum_final(bagian, saat_sesi) == "2026-09-11"
    assert len(bagian["tutup"]) == 1 and len(bagian["volume"]) == 1

    bagian2 = {"tutup": pd.DataFrame({"AAPL": [1.0, 2.0]}, index=idx)}
    malam = datetime(2026, 9, 11, 22, 17, tzinfo=timezone.utc)
    assert harga.buang_bar_belum_final(bagian2, malam) is None
