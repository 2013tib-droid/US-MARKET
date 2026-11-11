"""Rezim, momentum-crash guard, skor komposit, dan label status — semuanya
dengan deret harga buatan, tanpa jaringan."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from usmarket import keputusan, makro


def deret(nilai, mulai="2025-01-01"):
    idx = pd.bdate_range(mulai, periods=len(nilai))
    return pd.Series(nilai, index=idx, dtype=float)


def naik(n=400, awal=100.0, per_hari=0.001):
    return deret([awal * (1 + per_hari) ** i for i in range(n)])


# --- rezim ----------------------------------------------------------------

def test_risk_on_butuh_di_atas_kedua_ma_dan_vix_tenang():
    r = makro.tentukan(naik(), deret([15.0] * 400))
    assert r.nama == makro.RISK_ON
    assert r.bobot["Momentum"] == 30 and r.bobot["LowVol"] == 0


def test_vix_di_atas_25_membuat_risk_off_walau_spx_di_atas_ma200():
    r = makro.tentukan(naik(), deret([30.0] * 400))
    assert r.nama == makro.RISK_OFF
    # Bukan sekadar label: bobot momentum turun dan Low-Vol menyala.
    assert r.bobot["Momentum"] == 10 and r.bobot["LowVol"] == 15
    assert any("VIX" in a for a in r.alasan)


def test_spx_di_bawah_ma200_risk_off_walau_vix_tenang():
    harga = list(naik(300).values) + [100.0] * 100
    r = makro.tentukan(deret(harga), deret([12.0] * 400))
    assert r.nama == makro.RISK_OFF
    assert any("MA200" in a for a in r.alasan)


def test_tanpa_vix_tidak_bisa_risk_on_dan_alasannya_disebut():
    r = makro.tentukan(naik(), None)
    assert r.nama == makro.NETRAL
    assert any("VIX" in a for a in r.alasan)


def test_bobot_tiap_rezim_berjumlah_100():
    for nama, b in makro.BOBOT_REZIM.items():
        assert sum(b.values()) == 100, nama


# --- momentum-crash guard -------------------------------------------------

def jatuh_lalu_pantul(hari_sejak_dasar: int):
    """Setahun datar, jatuh 35%, lalu memantul 25% dari dasarnya."""
    datar = [100.0] * 260
    turun = list(np.linspace(100, 65, 40))
    pantul = list(np.linspace(65, 81.25, hari_sejak_dasar)) if hari_sejak_dasar else []
    return deret(datar + turun + pantul, mulai="2024-01-01")


def test_guard_menyala_pada_pantulan_cepat_setelah_jatuh_dalam():
    aktif, tanggal = makro.guard_momentum(jatuh_lalu_pantul(30))
    assert aktif and tanggal


def test_guard_tidak_menyala_tanpa_jatuh_dalam():
    aktif, _ = makro.guard_momentum(naik(400))
    assert not aktif


def test_guard_tidak_menyala_kalau_pantulannya_terlalu_kecil():
    datar = [100.0] * 260
    turun = list(np.linspace(100, 65, 40))
    pantul = list(np.linspace(65, 68, 20))  # +4,6%, di bawah ambang 15%
    aktif, _ = makro.guard_momentum(deret(datar + turun + pantul, mulai="2024-01-01"))
    assert not aktif


def test_guard_menang_atas_rezim_lain_dan_memotong_bobot_momentum():
    spx = jatuh_lalu_pantul(30)
    r = makro.tentukan(spx, deret([20.0] * len(spx), mulai="2024-01-01"))
    assert r.nama == makro.GUARD and r.guard_aktif
    assert r.bobot["Momentum"] == 10
    # Persis pelajaran 2009/2020: momentum dipotong, value dan smart money naik.
    assert r.bobot["Value"] == 30 and r.bobot["SmartMoney"] == 15


# --- breadth --------------------------------------------------------------

def test_breadth_menghitung_persen_di_atas_ma200():
    harga = pd.Series([10.0, 20.0, 30.0, 40.0])
    ma = pd.Series([5.0, 25.0, 25.0, np.nan])
    # Dari tiga yang MA200-nya terbaca, dua di atasnya.
    assert makro.breadth_di_atas_ma200(harga, ma) == pytest.approx(2 / 3 * 100)


# --- skor komposit --------------------------------------------------------

def tabel_uji():
    return pd.DataFrame({
        "Z_Quality": [2.0, 0.0, -1.0, np.nan],
        "Z_Momentum": [1.0, 2.0, -1.0, 1.0],
        "Z_Value": [0.0, 1.0, -2.0, np.nan],
        "Z_Growth": [1.0, 0.0, 0.0, np.nan],
        "Z_SmartMoney": [0.0, 0.0, 0.0, np.nan],
        "Z_LowVol": [-1.0, 0.0, 2.0, np.nan],
    }, index=pd.Index(list("ABCD"), name="Ticker"))


def test_skor_faktor_menormalisasi_ke_bobot_yang_terisi():
    t = tabel_uji()
    s = makro.skor_faktor(t, makro.BOBOT_REZIM[makro.RISK_ON])
    # D hanya punya momentum; skornya = z momentum × total bobot, bukan
    # dihukum seolah faktor lainnya bernilai nol.
    assert s["D"] == pytest.approx(1.0 * 100)
    assert s["A"] > s["C"]


def test_lowvol_tidak_ikut_di_risk_on_tapi_ikut_di_risk_off():
    """Dua emiten yang identik kecuali Low-Vol-nya: di risk-on skornya harus
    sama persis (bobot Low-Vol nol), di risk-off yang lebih tenang menang."""
    t = pd.DataFrame({
        "Z_Quality": [1.0, 1.0], "Z_Momentum": [1.0, 1.0], "Z_Value": [1.0, 1.0],
        "Z_Growth": [1.0, 1.0], "Z_SmartMoney": [0.0, 0.0], "Z_LowVol": [2.0, -2.0],
    }, index=pd.Index(["TENANG", "LIAR"], name="Ticker"))
    on = makro.skor_faktor(t, makro.BOBOT_REZIM[makro.RISK_ON])
    off = makro.skor_faktor(t, makro.BOBOT_REZIM[makro.RISK_OFF])
    assert on["TENANG"] == pytest.approx(on["LIAR"])
    assert off["TENANG"] > off["LIAR"]


def test_skor_persentil_selalu_0_sampai_100():
    s = makro.skor_persentil(pd.Series([-5.0, 0.0, 3.0, np.nan]))
    assert s.max() <= 100 and s.min() > 0 and pd.isna(s.iloc[-1])


# --- status ---------------------------------------------------------------

def baris_dasar(**ubah):
    r = {"Z_Quality": 2.0, "Z_Momentum": 2.0, "Z_Value": 2.0, "Z_Growth": 2.0,
         "Z_SmartMoney": 0.0, "Z_LowVol": 0.0, "Flag": "", "LolosLikuiditas": True,
         "TrendTemplate": True, "Hari_Ke_Earnings": 30.0, "Short_PctFloat": 3.0,
         "Harga": 100.0, "MA200": 90.0, "Insider_ClusterBuy": False}
    r.update(ubah)
    return r


def tabel_status(*baris):
    return pd.DataFrame(list(baris), index=pd.Index(
        [chr(65 + i) for i in range(len(baris))], name="Ticker"))


def test_akumulasi_butuh_skor_tinggi_tanpa_flag_dan_tren_lolos():
    t = tabel_status(baris_dasar(), baris_dasar(Z_Quality=-3.0, Z_Momentum=-3.0,
                                               Z_Value=-3.0, Z_Growth=-3.0))
    hasil = keputusan.hitung(t, makro.Rezim(nama=makro.RISK_ON))
    assert hasil.loc["A", "Status"] == keputusan.AKUMULASI
    assert "tren lolos" in hasil.loc["A", "Alasan"]


def test_tren_belum_konfirmasi_jadi_pantau_bukan_akumulasi():
    t = tabel_status(baris_dasar(TrendTemplate=False), baris_dasar(Z_Quality=-3.0,
                     Z_Momentum=-3.0, Z_Value=-3.0, Z_Growth=-3.0))
    hasil = keputusan.hitung(t, makro.Rezim(nama=makro.RISK_ON))
    assert hasil.loc["A", "Status"] == keputusan.PANTAU


def test_flag_berat_jadi_hindari_berapa_pun_skornya():
    t = tabel_status(baris_dasar(Flag="DISTRES"), baris_dasar(Z_Momentum=-3.0))
    hasil = keputusan.hitung(t, makro.Rezim(nama=makro.RISK_ON))
    assert hasil.loc["A", "Status"] == keputusan.HINDARI
    assert "DISTRES" in hasil.loc["A", "Alasan"]


def test_short_ekstrem_jadi_hindari_walau_skornya_puncak():
    t = tabel_status(baris_dasar(Short_PctFloat=36.0), baris_dasar(Z_Momentum=-3.0))
    hasil = keputusan.hitung(t, makro.Rezim(nama=makro.RISK_ON))
    assert hasil.loc["A", "Status"] == keputusan.HINDARI
    assert "short" in hasil.loc["A", "Alasan"]


def test_lapkeu_dekat_menunda_apa_pun_skornya():
    t = tabel_status(baris_dasar(Hari_Ke_Earnings=3.0), baris_dasar(Z_Momentum=-3.0))
    hasil = keputusan.hitung(t, makro.Rezim(nama=makro.RISK_ON))
    assert hasil.loc["A", "Status"] == keputusan.TUNGGU_LAPKEU
    assert "lapkeu" in hasil.loc["A", "Alasan"]


def test_lapkeu_dekat_tidak_menyelamatkan_yang_kena_flag_berat():
    """TUNGGU-LAPKEU pada emiten ber-flag berat akan menyiratkan ia layak
    dibeli setelah lapkeu. Yang benar tetap HINDARI."""
    t = tabel_status(baris_dasar(Hari_Ke_Earnings=3.0, Flag="DISTRES"),
                     baris_dasar(Z_Momentum=-3.0))
    hasil = keputusan.hitung(t, makro.Rezim(nama=makro.RISK_ON))
    assert hasil.loc["A", "Status"] == keputusan.HINDARI


def test_tanpa_rezim_memakai_bobot_netral_dan_menyebutnya():
    hasil = keputusan.hitung(tabel_status(baris_dasar(), baris_dasar(Z_Momentum=-3.0)))
    assert (hasil["Rezim"] == makro.NETRAL).all()


def test_alasan_menyebut_faktor_yang_berbobot_di_rezimnya():
    """Low-Vol berbobot 0 di risk-on, jadi ia tidak boleh disebut sebagai
    kekuatan di sana walau z-nya paling tinggi."""
    t = tabel_status(baris_dasar(Z_LowVol=3.0, Z_Quality=0.6, Z_Momentum=0.1,
                                 Z_Value=0.1, Z_Growth=0.1),
                     baris_dasar(Z_Momentum=-3.0))
    hasil = keputusan.hitung(t, makro.Rezim(nama=makro.RISK_ON))
    assert "lowvol" not in hasil.loc["A", "Alasan"].lower()
    assert "quality" in hasil.loc["A", "Alasan"].lower()
