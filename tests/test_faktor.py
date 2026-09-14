import numpy as np
import pandas as pd
import pytest

from usmarket import faktor


def seri(nilai, mulai="2024-01-01"):
    return pd.Series(nilai, index=pd.bdate_range(mulai, periods=len(nilai)), dtype=float)


def test_momentum_12_1_melewati_bulan_terakhir():
    # Naik 0,1%/hari selama 252 hari, lalu anjlok 20% di 21 hari terakhir.
    naik = 100 * 1.001 ** np.arange(253)
    turun = naik[-1] * np.linspace(1, 0.8, 22)[1:]
    adj = seri(np.concatenate([naik, turun]))
    m = faktor.mentah_momentum(adj)
    # Dari t-252 sampai t-21 = 231 hari naik; anjloknya tidak ikut terhitung.
    harapan = (1.001 ** 231 - 1) * 100
    assert m["Ret12_1"] == pytest.approx(harapan, rel=1e-6)


def test_momentum_data_kurang_nan():
    m = faktor.mentah_momentum(seri(np.ones(200)))
    assert np.isnan(m["Ret12_1"]) and np.isnan(m["Ret6_1"])


def test_beta_dua_kali_pasar():
    rng = np.random.default_rng(1)
    r_spy = rng.normal(0, 0.01, 400)
    spy = seri(100 * np.cumprod(1 + r_spy))
    saham = seri(100 * np.cumprod(1 + 2 * r_spy))
    lv = faktor.mentah_lowvol(saham, spy)
    # Mingguan, jadi bukan tepat 2: return harian 2× yang dimajemukkan
    # seminggu tidak persis 2× return mingguan pasar.
    assert lv["Beta"] == pytest.approx(2.0, rel=0.05)


def test_beta_butuh_setahun_mingguan():
    spy = seri(100 * 1.001 ** np.arange(200))
    assert np.isnan(faktor.beta_mingguan(spy, spy))


def test_max_drawdown():
    nilai = np.concatenate([np.full(100, 100.0), np.full(50, 60.0), np.full(110, 90.0)])
    lv = faktor.mentah_lowvol(seri(nilai), None)
    assert lv["MaxDD1T"] == pytest.approx(-40.0)


def test_z_sektor_per_kelompok_dan_pangkas():
    sektor = pd.Series(["A"] * 6 + ["B"] * 6)
    nilai = pd.Series([1, 2, 3, 4, 5, 6, 100, 200, 300, 400, 500, 600], dtype=float)
    z, kecil = faktor.z_sektor(nilai, sektor)
    # Z identik di dua sektor karena bentuk sebarannya sama, meski skalanya 100×.
    assert np.allclose(z[:6].values, z[6:].values)
    assert abs(z[:6].mean()) < 1e-12
    assert not kecil.any()

    pencilan = pd.Series([0.0] * 20 + [1000.0])
    z2, _ = faktor.z_sektor(pencilan, pd.Series(["A"] * 21))
    assert z2.max() == faktor.BATAS_Z


def test_sektor_kecil_diukur_terhadap_universe():
    sektor = pd.Series(["A"] * 10 + ["B"] * 2)
    nilai = pd.Series(list(range(10)) + [50, 60], dtype=float)
    z, kecil = faktor.z_sektor(nilai, sektor)
    assert kecil.tolist() == [False] * 10 + [True] * 2
    assert z.iloc[-1] > 1  # jauh di atas rata-rata universe, bukan z=+0,7 di sektor 2 saham


def test_gabung_z_nan_bila_satu_komponen_kosong():
    sektor = pd.Series(["A"] * 6)
    a = pd.Series([1, 2, 3, 4, 5, 6], dtype=float)
    b = pd.Series([1, 2, np.nan, 4, 5, 6], dtype=float)
    z, _ = faktor.gabung_z([a, b], sektor)
    assert np.isnan(z.iloc[2])
    assert z.dropna().std() == pytest.approx(1.0)


def test_rs_rating_rentang_1_sampai_99():
    r = faktor.rs_rating(pd.Series(np.linspace(-0.5, 0.5, 200)))
    assert r.min() >= 1 and r.max() == 99
    assert r.is_monotonic_increasing
