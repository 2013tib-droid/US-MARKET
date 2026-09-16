"""Uji jalur pengunduhan Form 4 tanpa menyentuh jaringan: klien EDGAR diberi
jawaban tiruan, dan skrip pembaru dijalankan terhadap klien itu."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from usmarket import sec, smartmoney

AKAR = Path(__file__).resolve().parent.parent


def modul_skrip(nama: str):
    spec = importlib.util.spec_from_file_location(nama, AKAR / "scripts" / f"{nama}.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules[nama] = modul
    spec.loader.exec_module(modul)
    return modul


perbarui = modul_skrip("perbarui_smartmoney")


class Jawaban:
    def __init__(self, isi=b"", status=200, json_=None):
        self.content, self.status_code, self._json = isi, status, json_

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def klien_tiruan(jawab) -> sec.KlienSEC:
    klien = sec.KlienSEC(user_agent="uji nama@contoh.com")
    klien.get = jawab
    return klien


SUBMISSIONS = {"filings": {"recent": {
    "accessionNumber": ["0001-24-000001", "0001-24-000002", "0001-24-000003"],
    "filingDate": ["2026-09-10", "2026-05-01", "2026-09-12"],
    "reportDate": ["2026-09-08", "2026-04-29", "2026-09-10"],
    "form": ["4", "4", "10-Q"],
    "primaryDocument": ["xslF345X05/wk-form4_1.xml", "xslF345X05/wk-form4_2.xml", "aapl-20260910.htm"],
}}}


def test_filing_terbaru_menyaring_form_dan_tanggal():
    klien = klien_tiruan(lambda url, **k: Jawaban(json_=SUBMISSIONS))
    hasil = klien.filing_terbaru(320193, {"4", "4/A"}, date(2026, 8, 1))
    assert [f["akses"] for f in hasil] == ["0001-24-000001"]
    assert hasil[0]["tanggal_periode"] == "2026-09-08"


def test_submissions_tanpa_blok_recent_tidak_melempar():
    klien = klien_tiruan(lambda url, **k: Jawaban(json_={"filings": {}}))
    assert klien.filing_terbaru(1, {"4"}, date(2026, 1, 1)) == []


def test_dokumen_mengambil_xml_asli_bukan_versi_terjemahan():
    dipanggil = []

    def jawab(url, **k):
        dipanggil.append(url)
        return Jawaban(isi=b"<ownershipDocument/>")

    klien = klien_tiruan(jawab)
    klien.dokumen(320193, "0001-24-000001", "xslF345X05/wk-form4_1.xml")
    assert dipanggil == ["https://www.sec.gov/Archives/edgar/data/320193/000124000001/wk-form4_1.xml"]


FORM4_XML = b"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>0000320193</issuerCik><issuerTradingSymbol>AAPL</issuerTradingSymbol></issuer>
  <reportingOwner><reportingOwnerId><rptOwnerCik>0001214156</rptOwnerCik>
    <rptOwnerName>COOK TIMOTHY D</rptOwnerName></reportingOwnerId></reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction>
    <transactionDate><value>2026-09-08</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>500</value></transactionShares>
      <transactionPricePerShare><value>200</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>"""


class KlienPalsu:
    """Klien EDGAR tiruan yang mencatat dokumen apa saja yang diminta."""

    def __init__(self):
        self.diminta = []

    def filing_terbaru(self, cik, form, sejak):
        return [{"akses": "0001-24-000001", "tanggal_lapor": "2026-09-10",
                 "tanggal_periode": "2026-09-08", "form": "4", "dokumen": "wk-form4_1.xml"},
                {"akses": "0001-24-000009", "tanggal_lapor": "2026-09-11",
                 "tanggal_periode": "2026-09-09", "form": "4", "dokumen": "wk-form4_9.xml"}]

    def dokumen(self, cik, akses, berkas):
        self.diminta.append(akses)
        return FORM4_XML


def test_unduh_form4_melewati_nomor_akses_yang_sudah_tersimpan():
    klien = KlienPalsu()
    baris, meta = perbarui.unduh_form4(klien, {320193: ["AAPL"]}, {"0001-24-000001"},
                                       date(2026, 6, 17), pekerja=2, maks_per_emiten=400)
    assert klien.diminta == ["0001-24-000009"]
    assert meta["filing_baru"] == 1 and meta["transaksi_baru"] == 1
    (t,) = baris
    assert t["Ticker"] == "AAPL" and t["Kode"] == "P" and t["Nilai"] == 100_000
    assert t["Akses"] == "0001-24-000009" and t["Tanggal_Lapor"] == "2026-09-11"


def test_jadwal_earnings_surprise_dan_tanggal_berikutnya():
    jadwal = pd.DataFrame(
        {"EPS Estimate": [1.0, 1.2, 1.5], "Reported EPS": [1.1, 1.1, None],
         "Surprise(%)": [10.0, -8.33, None]},
        index=pd.to_datetime(["2026-03-01", "2026-06-01", "2026-11-01"], utc=True))
    r = perbarui.dari_jadwal_earnings(jadwal, pd.Timestamp("2026-09-15", tz="UTC"))
    assert r["Surprise_Terakhir"] == -8.33
    assert r["Surprise_Rata4Q"] == pytest.approx(0.835)
    assert r["Surprise_Tanggal"] == "2026-06-01"
    assert r["Earnings_Berikut"] == "2026-11-01"


# --- pengulangan Yahoo ------------------------------------------------------

class GalatLaju(Exception):
    """Meniru yfinance.exceptions.YFRateLimitError, yang tidak diimpor di sini
    supaya ujinya tidak ikut berubah kalau nama kelasnya berubah."""


def test_layak_diulang_membedakan_galat_sementara_dari_yang_permanen():
    assert perbarui.layak_diulang(GalatLaju("rate limited"))
    assert perbarui.layak_diulang(TimeoutError("read timeout"))
    assert not perbarui.layak_diulang(KeyError("delisted"))
    assert not perbarui.layak_diulang(ValueError("JSON rusak"))


def test_dari_yahoo_mengulang_galat_sementara_dan_menyerah_pada_yang_permanen(monkeypatch):
    """Run 15 Sep 2026 kehilangan 375 emiten karena pembatasan laju Yahoo.
    Yang gagal sementara harus dicoba lagi; yang gagal permanen tidak."""
    percobaan = {}

    class TickerPalsu:
        def __init__(self, t):
            self.t = t
            percobaan[t] = percobaan.get(t, 0) + 1

        @property
        def info(self):
            if self.t == "SEKALI_GAGAL" and percobaan[self.t] == 1:
                raise GalatLaju("Too Many Requests")
            if self.t == "SELALU_GAGAL":
                raise KeyError("delisted")
            return {"heldPercentInstitutions": 0.5, "targetMeanPrice": 10.0}

        @property
        def earnings_dates(self):
            return None

    monkeypatch.setitem(sys.modules, "yfinance", type("m", (), {"Ticker": TickerPalsu}))
    tabel = perbarui.dari_yahoo(["OK", "SEKALI_GAGAL", "SELALU_GAGAL"], pekerja=1,
                                tidur=lambda _: None)

    # Yang sempat kena batas laju akhirnya terisi, dan persen Yahoo (pecahan)
    # sudah dikali 100.
    assert tabel.loc["SEKALI_GAGAL", "Institusi_Pct"] == 50.0
    assert percobaan["SEKALI_GAGAL"] == 2
    # Yang permanen tidak diulang sama sekali, dan alasannya tercatat.
    assert percobaan["SELALU_GAGAL"] == 1
    assert tabel.loc["SELALU_GAGAL", "Catatan_SM"] == "yahoo gagal: KeyError"
    assert tabel.loc["OK", "Target_Rata"] == 10.0


# --- lapis verifikasi tanpa jaringan ----------------------------------------

verifikasi = modul_skrip("verifikasi_smartmoney")


def _transaksi(ticker, tanggal, pemilik_cik, nilai, kode="P", rencana=False):
    return {"Ticker": ticker, "CIK": 1, "Akses": "0001-26-000001", "Tanggal": tanggal,
            "Tanggal_Lapor": tanggal, "Kode": kode, "Lembar": 100.0, "Harga": nilai / 100,
            "Nilai": nilai, "Arah": "A", "Pemilik": f"Orang {pemilik_cik}",
            "Pemilik_CIK": pemilik_cik, "Jabatan": "Direktur", "Peran": "director",
            "Rencana10b5": rencana}


def test_rekonsiliasi_menangkap_agregat_yang_tidak_cocok(capsys):
    insider = pd.DataFrame([_transaksi("AAA", "2026-09-01", 11, 1_000_000.0),
                            _transaksi("AAA", "2026-09-05", 22, 2_000_000.0)])
    ringkas = smartmoney.ringkas_insider(insider, hari_ini=date(2026, 9, 15))

    assert verifikasi.rekonsiliasi(ringkas, insider, date(2026, 9, 15))

    rusak = ringkas.copy()
    rusak.loc["AAA", "Insider_Net90H_JutaUSD"] = 99.0
    assert not verifikasi.rekonsiliasi(rusak, insider, date(2026, 9, 15))
    assert "BEDA di 1 emiten" in capsys.readouterr().out


def test_bukti_cluster_menolak_tanda_yang_tidak_didukung_transaksinya(capsys):
    # Satu pelapor yang membeli dua kali bukan cluster; kalau kolomnya
    # terlanjur bertanda True, pemeriksaan ini yang harus menangkapnya.
    insider = pd.DataFrame([_transaksi("BBB", "2026-09-01", 11, 1_000_000.0),
                            _transaksi("BBB", "2026-09-05", 11, 2_000_000.0)])
    sm = pd.DataFrame({"Insider_ClusterBuy": [True], "Insider_ClusterTgl": ["2026-09-05"],
                       "Insider_Beli90H_JutaUSD": [3.0]}, index=pd.Index(["BBB"], name="Ticker"))
    assert not verifikasi.bukti_cluster(sm, insider)
    assert "['BBB']" in capsys.readouterr().out
