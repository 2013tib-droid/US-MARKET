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


def test_bar_terakhir_tanpa_penutupan_ditambal_dari_data_per_jam():
    idx = pd.DatetimeIndex(["2026-09-11", "2026-09-14"])
    def df(a, b):
        return pd.DataFrame({"AAPL": [a[0], a[1]], "SPY": [b[0], b[1]]}, index=idx)
    bagian = {"buka": df((327.0, 334.8), (760.0, 759.0)), "tinggi": df((336.0, np.nan), (766.0, np.nan)),
              "rendah": df((326.0, np.nan), (757.0, np.nan)), "tutup": df((332.27, np.nan), (764.29, np.nan)),
              "tutup_adj": df((332.27, np.nan), (764.29, np.nan)), "volume": df((5e7, 3.9e7), (4.5e7, 4.4e7))}
    jam_idx = pd.DatetimeIndex(["2026-09-14 09:30", "2026-09-14 15:30"]).tz_localize("America/New_York")
    per_jam = {"Open": pd.DataFrame({"AAPL": [333.2, 334.4], "SPY": [758.8, 761.7]}, index=jam_idx),
               "High": pd.DataFrame({"AAPL": [335.5, 334.9], "SPY": [763.5, 762.0]}, index=jam_idx),
               "Low": pd.DataFrame({"AAPL": [331.3, 332.9], "SPY": [757.9, 760.1]}, index=jam_idx),
               "Close": pd.DataFrame({"AAPL": [333.0, 333.05], "SPY": [759.6, 760.77]}, index=jam_idx)}
    catatan = harga.tambal_bar_terakhir(bagian, ambil=lambda t: per_jam)
    assert catatan == "2026-09-14: 2 ticker"
    assert bagian["tutup"].loc["2026-09-14", "AAPL"] == 333.05
    assert bagian["tutup_adj"].loc["2026-09-14", "SPY"] == 760.77
    assert bagian["tinggi"].loc["2026-09-14", "AAPL"] == 335.5
    assert bagian["buka"].loc["2026-09-14", "AAPL"] == 334.8  # open harian yang ada tidak ditimpa


def test_bar_lengkap_tidak_ditambal():
    idx = pd.DatetimeIndex(["2026-09-11", "2026-09-14"])
    bagian = {k: pd.DataFrame({"AAPL": [1.0, 2.0]}, index=idx)
              for k in ("buka", "tinggi", "rendah", "tutup", "tutup_adj", "volume")}
    assert harga.tambal_bar_terakhir(bagian, ambil=lambda t: (_ for _ in ()).throw(AssertionError)) is None
