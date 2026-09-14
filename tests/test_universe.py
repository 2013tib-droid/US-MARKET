import pandas as pd
import pytest

from usmarket import universe


def html_tabel(baris, kolom=("Symbol", "Security", "GICS Sector", "GICS Sub-Industry")):
    kepala = "".join(f"<th>{k}</th>" for k in kolom)
    isi = "".join("<tr>" + "".join(f"<td>{v}</td>" for v in b) + "</tr>" for b in baris)
    return f'<table id="constituents"><tr>{kepala}</tr>{isi}</table>'


def test_normalisasi_ticker():
    assert universe.normalisasi_ticker("BRK.B") == "BRK-B"
    assert universe.normalisasi_ticker(" bf.b[1] ") == "BF-B"


def test_urai_tabel_dan_validasi_jumlah():
    sumber = universe.SumberIndeks("UJI", "-", "Symbol", "Security", "GICS Sector",
                                   "GICS Sub-Industry", 2, 5)
    html = html_tabel([("AAPL", "Apple", "Information Technology", "Hardware"),
                       ("BRK.B", "Berkshire", "Financials", "Insurance"),
                       ("BRK.B", "Berkshire", "Financials", "Insurance")])
    df = universe.urai_tabel(html, sumber)
    assert list(df["Ticker"]) == ["AAPL", "BRK-B"]

    with pytest.raises(universe.TabelTidakWajar):
        universe.urai_tabel(html_tabel([("AAPL", "Apple", "IT", "HW")]), sumber)


def test_kolom_hilang_ditolak():
    sumber = universe.SUMBER["SP500"]
    with pytest.raises(universe.TabelTidakWajar):
        universe.urai_tabel(html_tabel([("A", "B", "C")], kolom=("Symbol", "Security", "X")), sumber)


def test_icb_dipetakan_ke_gics():
    sumber = universe.SumberIndeks("NDXUJI", "-", "Ticker", "Company", "ICB Industry",
                                   "ICB Subsector", 1, 5)
    html = html_tabel([("ASML", "ASML", "Technology", "Semis"), ("XYZ", "X", "Aneh", "-")],
                      kolom=("Ticker", "Company", "ICB Industry[1]", "ICB Subsector[1]"))
    df = universe.urai_tabel(html, sumber).set_index("Ticker")
    assert df.loc["ASML", "Sektor"] == "Information Technology"
    assert df.loc["XYZ", "Sektor"] == universe.SEKTOR_TAK_DIKETAHUI


def test_gabung_mendahulukan_gics_dan_mencatat_keanggotaan():
    sp500 = pd.DataFrame([{"Ticker": "AAPL", "Nama": "Apple Inc.", "Sektor": "Information Technology",
                           "Industri": "Technology Hardware"}])
    ndx = pd.DataFrame([{"Ticker": "AAPL", "Nama": "Apple", "Sektor": "Information Technology",
                         "Industri": "Computer Hardware"},
                        {"Ticker": "ASML", "Nama": "ASML", "Sektor": "Information Technology",
                         "Industri": "Semis"}])
    df = universe.gabung({"SP500": sp500, "NDX": ndx}, ["AAPL", "PLTR"])
    assert df.loc["AAPL", "Indeks"] == "SP500;NDX;WATCH"
    assert df.loc["AAPL", "Industri"] == "Technology Hardware"
    assert df.loc["PLTR", "Sektor"] == universe.SEKTOR_TAK_DIKETAHUI


def test_baca_daftar_ticker_abaikan_komentar(tmp_path):
    p = tmp_path / "w.txt"
    p.write_text("# komentar\nbrk.b\n\nPLTR  # catatan\n", encoding="utf-8")
    assert universe.baca_daftar_ticker(p) == ["BRK-B", "PLTR"]
